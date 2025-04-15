import logging
import os
import requests
import psycopg2
from bs4 import BeautifulSoup
from datetime import datetime
from psycopg2.extras import DictCursor
from urllib.parse import urljoin


# logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

TAGESSCHAU_URL = 'https://www.tagesschau.de/'
USER_AGENT = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/58.0.3029.110 Safari/537.3' # I am not a robot

DB_HOST = os.environ.get('DB_HOST', 'postgres')
DB_PORT = os.environ.get('DB_PORT', '5432')
DB_NAME = os.environ.get('DB_NAME', 'tagesschau')
DB_USER = os.environ.get('DB_USER', 'postgres')
DB_PASSWORD = os.environ.get('DB_PASSWORD', 'postgres')


def get_db_connection():
    """ connect to db """
    try:
        conn = psycopg2.connect(
            host=DB_HOST,
            port=DB_PORT,
            dbname=DB_NAME,
            user=DB_USER,
            password=DB_PASSWORD
        )
        return conn
    except Exception as e:
        logger.error(f'Database connection error: {e}')
        raise


def crawl_article_page(url):
    """ get content from an article page """
    logger.info(f'Crawling article page: {url}')

    try:
        headers = {'User-Agent': USER_AGENT}
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()

        soup = BeautifulSoup(response.text, 'html.parser')

        headline_elem = soup.select_one('.seitenkopf__headline--text')
        headline = headline_elem.get_text(strip=True) if headline_elem else 'No headline found'

        sub_headline_elem = soup.select_one('.seitenkopf__topline')
        sub_headline = sub_headline_elem.get_text(strip=True) if sub_headline_elem else ''

        article_body = soup.select_one('div.article__body')
        if article_body:
            content_elems = article_body.find_all('p')
        elif soup.select('p.textabsatz'):
            content_elems = soup.select('p.textabsatz')
        else:
            content_elems = []

        content = '\n\n'.join(p.get_text(strip=True) for p in content_elems)
        if not content:
            logger.warning(f'No content found for {url}')
            content = 'No content found'

        updated_at = None
        updated_at_elem = soup.select_one('.metatextline')
        if updated_at_elem:
            date_text_raw = updated_at_elem.get_text(strip=True)
            date_text = date_text_raw.replace('Stand:', '').replace('Uhr', '').strip()

            try:
                updated_at = datetime.strptime(date_text, '%d.%m.%Y %H:%M').isoformat()
            except ValueError:
                logger.warning('Can not parse date, skipping')
                updated_at = None
        if not updated_at:
            logger.warning(f'No updated_at element found for {url}')

        return {
            'url': url,
            'headline': headline,
            'sub_headline': sub_headline,
            'content': content,
            'updated_at': updated_at,
        }

    except Exception as e:
        logger.error(f'Crawling article page error: {e}')
        return None


def store_article(article_data):
    """ store article data in db with version history """
    if not article_data:
        return False

    conn = get_db_connection()
    try:
        with conn.cursor(cursor_factory=DictCursor) as cursor:
            # check for existing
            cursor.execute(
                'SELECT * FROM articles WHERE url = %s', (article_data['url'],)
            )
            existing_article = cursor.fetchone()

            if existing_article:
                if (existing_article['headline'] != article_data['headline'] or
                    existing_article['sub_headline'] != article_data['sub_headline'] or
                    existing_article['content'] != article_data['content']):

                    # store old version
                    cursor.execute(
                        """
                        INSERT INTO articles_versions (article_id, headline, sub_headline, content, crawled_at)
                        VALUES (%s, %s, %s, %s, %s)
                        """,
                        (
                            existing_article['id'],
                            existing_article['headline'],
                            existing_article['sub_headline'],
                            existing_article['content'],
                            existing_article['last_crawled_at']
                        )
                    )

                    # update current version
                    cursor.execute(
                        """
                        UPDATE articles
                        SET headline = %s, sub_headline = %s, content = %s, updated_at = %s, last_crawled_at = NOW()
                        WHERE id = %s 
                        """,
                        (
                            article_data['headline'],
                            article_data['sub_headline'],
                            article_data['content'],
                            article_data['updated_at'],
                            existing_article['id']
                        )
                    )

                    logger.info(f'Updated article {existing_article['id']} with new version')
                    conn.commit()
                    return True
                else:
                    # just update last_crawled_at
                    cursor.execute(
                        'UPDATE articles SET last_crawled_at = NOW() WHERE id = %s',
                        (existing_article['id'],)
                    )
                    logger.info(f'Article {existing_article['id']} unchanged')
                    conn.commit()
                    return False
            else:
                # new article
                cursor.execute(
                    """
                    INSERT INTO articles (url, headline, sub_headline, content, updated_at)
                    VALUES (%s, %s, %s, %s, %s)
                    RETURNING id
                    """,
                    (
                        article_data['url'],
                        article_data['headline'],
                        article_data['sub_headline'],
                        article_data['content'],
                        article_data['updated_at']
                    )
                )
                article_id = cursor.fetchone()[0]
                logger.info(f'Inserted new article {article_id}')
                conn.commit()
                return True

    except Exception as e:
        conn.rollback()
        logger.error(f'Error storing article: {e}')
        return False
    finally:
        conn.close()

def extract_article_links(overview_html):
    """ extract article links from overview page """
    soup = BeautifulSoup(overview_html, 'html.parser')

    links = []

    link_elems = soup.select('.teaser__link')

    for link_elem in link_elems:
        if link_elem.has_attr('href'):
            href = link_elem['href']
            href = urljoin(TAGESSCHAU_URL, href)
            links.append(href)

    return list(set(links))


def crawl_overview_page():
    """ crawl the overview page and process all articles"""
    logger.info(f'Starting overview page crawl')

    try:
        headers = {'User-Agent': USER_AGENT}
        response = requests.get(TAGESSCHAU_URL, headers=headers, timeout=10)
        response.raise_for_status()

        article_links = extract_article_links(response.text)
        logger.info(f'Found {len(article_links)} article links')

        new_versions_count = 0
        for link in article_links:
            article_data = crawl_article_page(link)
            if article_data and store_article(article_data):
                new_versions_count += 1

        logger.info(f'Crawl complete. Found {new_versions_count} new versions')

        conn = get_db_connection()
        try:
            with conn.cursor(cursor_factory=DictCursor) as cursor:
                cursor.execute(
                    'UPDATE crawler_config SET last_run = NOW() WHERE id =1'
                )
                conn.commit()
        finally:
            conn.close()

        return new_versions_count

    except Exception as e:
        logger.error(f'Error crawling page: {e}')
        return 0


def crawl_single_article(url):
    """ crawl an article by url """
    logger.info(f'Starting single article crawl: {url}')
    article_data = crawl_article_page(url)
    if article_data and store_article(article_data):
        return True
    return False
