import os
import logging
import psycopg2
from flask import Flask, request, jsonify
from psycopg2.extras import DictCursor

# logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

DB_HOST = os.environ.get('DB_HOST', 'postgres')
DB_PORT = os.environ.get('DB_PORT', '5432')
DB_NAME = os.environ.get('DB_NAME', 'tagesschau')
DB_USER = os.environ.get('DB_USER', 'user')
DB_PASSWORD = os.environ.get('DB_PASSWORD', 'password')

app = Flask(__name__)


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


@app.route('/health', methods=['GET'])
def health_check():
    """ health check ep """
    return jsonify({'status': 'healthy'})


@app.route('/api/articles', methods=['GET'])
def list_articles():
    """ list all articles """
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 10, type=int)

    if per_page > 100:
        per_page = 100

    offset = (page - 1) * per_page

    conn = get_db_connection()
    try:
        with conn.cursor(cursor_factory=DictCursor) as cursor:
            # get total for pagination
            cursor.execute('SELECT COUNT(*) FROM articles')
            total_count = cursor.fetchone()[0]

            # get articles
            cursor.execute(
                """
                SELECT id, url, headline, sub_headline,
                        first_crawled_at, last_crawled_at, updated_at,
                        (SELECT COUNT(*) FROM articles_versions WHERE article_id = article_id) AS version_count
                FROM articles
                ORDER BY last_crawled_at DESC
                LIMIT %s OFFSET %s
                """,
                (per_page, offset)
            )

            articles = []
            for row in cursor.fetchall():
                article = dict(row)
                # convert timestamps
                article['first_crawled_at'] = article['first_crawled_at'].isoformat()
                article['last_crawled_at'] = article['last_crawled_at'].isoformat()
                article['updated_at'] = article['updated_at'].isoformat() if article['updated_at'] else None
                articles.append(article)

            return jsonify({
                'total': 'total_count',
                'page': page,
                'per_page': per_page,
                'total_pages': (total_count + per_page - 1) // per_page,
                'articles': articles,
            })
    finally:
        conn.close()


@app.route('/api/articles/<int:article_id>', methods=['GET'])
def get_article(article_id):
    """ get article details """
    conn = get_db_connection()
    try:
        with conn.cursor(cursor_factory=DictCursor) as cursor:
            cursor.execute(
                'SELECT * FROM articles WHERE id = %s',
                (article_id,)
            )
            article_row = cursor.fetchone()

            if not article_row:
                return jsonify({'status': 'error', 'message': 'article not found'}), 404

            article = dict(article_row)
            # convert timestamps
            article['first_crawled_at'] = article['first_crawled_at'].isoformat()
            article['last_crawled_at'] = article['last_crawled_at'].isoformat()
            article['updated_at'] = article['updated_at'].isoformat() if article['updated_at'] else None

            cursor.execute(
                'SELECT COUNT(*) FROM articles_versions WHERE article_id = %s',
                (article_id,)
            )
            version_count = cursor.fetchone()[0]

            return jsonify({
                'article': article,
                'version_count': version_count,
            })
    finally:
        conn.close()

@app.route('/api/articles/<int:article_id>/versions', methods=['GET'])
def get_article_versions(article_id):
    """ get article versions """
    conn = get_db_connection()
    try:
        with conn.cursor(cursor_factory=DictCursor) as cursor:
            cursor.execute(
                'SELECT * FROM articles WHERE id = %s',
                (article_id,)
            )
            if not cursor.fetchone():
                return jsonify({'status': 'error', 'message': f'article {article_id} not found'}), 404

            # get all versions
            cursor.execute(
                """
                SELECT id, headline, sub_headline, content, crawled_at
                FROM articles_versions
                WHERE article_id = %s
                ORDER BY crawled_at DESC
                """,
                (article_id,)
            )

            versions = []
            for row in cursor.fetchall():
                version = dict(row)
                version['crawled_at'] = version['crawled_at'].isoformat()
                versions.append(version)

            return jsonify({
                'article_id': article_id,
                'versions': versions,
                'version_count': len(versions),
            })
    finally:
        conn.close()


@app.route('/api/articles/<int:article_id>/changes', methods=['GET'])
def get_article_changes(article_id):
    """ check an article for changes over time """
    conn = get_db_connection()
    try:
        with conn.cursor(cursor_factory=DictCursor) as cursor:
            cursor.execute(
                'SELECT * FROM articles WHERE id = %s',
                (article_id,)
            )
            if not cursor.fetchone():
                return jsonify({'status': 'error', 'message': f'article {article_id} not found'}), 404

            # get all versions
            cursor.execute(
                'SELECT COUNT(*) FROM articles_versions WHERE article_id = %s',
                (article_id,)
            )
            version_count = cursor.fetchone()[0]

            has_changed = version_count > 0

            return jsonify({
                'article_id': article_id,
                'has_changed': has_changed,
                'version_count': version_count,
            })
    finally:
        conn.close()


@app.route('/api/search', methods=['GET'])
def search_articles():
    """ search articles by keyword """
    query = request.args.get('q', '')
    if not query or len(query.strip()) < 2:
        return jsonify({'status': 'error', 'message': 'keyword must be at least 2 characters'}), 400

    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 10, type=int)

    if per_page > 100:
        per_page = 100

    offset = (page - 1) * per_page

    conn = get_db_connection()
    try:
        with conn.cursor(cursor_factory=DictCursor) as cursor:
            # get count of matching articles
            cursor.execute(
                """
                SELECT COUNT(*) 
                FROM articles
                WHERE 
                    to_tsvector('german', headline) @@ plainto_tsquery('german', %s)
                    OR to_tsvector('german', sub_headline) @@ plainto_tsquery('german', %s)
                    OR to_tsvector('german', content) @@ plainto_tsquery('german', %s)
                """,
                (query, query, query)
            )
            total_count = cursor.fetchone()[0]

            # get matching articles
            cursor.execute(
                """
                SELECT id, url, headline, sub_headline, ts_headline('german', content, plainto_tsquery('german', %s), 'MaxFragments=2, FragmentDelimiter=' ... '') as content_excerpt,
                first_crawled_at, last_crawled_at, updated_at
                FROM articles
                WHERE
                    to_tsvector('german', headline) @@ plainto_tsquery('german', %s)
                    OR to_tsvector('german', sub_headline) @@ plainto_tsquery('german', %s)
                    OR to_tsvector('german', content) @@ plainto_tsquery('german', %s)
                ORDER BY updated_at DESC NULLS LAST
                LIMIT %s OFFSET %s
                """,
                (query, query, query, query, per_page, offset)
            )

            results = []
            for row in cursor.fetchall():
                result = dict(row)
                # convert timestamps
                result['first_crawled_at'] = result['first_crawled_at'].isoformat()
                result['last_crawled_at'] = result['last_crawled_at'].isoformat()
                result['updated_at'] = result['updated_at'].isoformat() if result['updated_at'] else None
                results.append(result)

            return jsonify({
                'query': query,
                'total': total_count,
                'page': page,
                'per_page': per_page,
                'total_pages': (total_count + per_page - 1) // per_page,
                'results': results
            })
    finally:
        conn.close()


@app.errorhandler(400)
def handle_bad_request(e):
    return jsonify({
        'status': 'error',
        'message': str(e),
    }), 400


@app.errorhandler(404)
def handle_not_found(e):
    return jsonify({
        'status': 'error',
        'message': 'Resource not found',
    }), 404


@app.errorhandler(500)
def handle_server_error(e):
    logger.error(f'Server error: {e}')
    return jsonify({
        'status': 'error',
        'message': 'Internal server error',
    }), 500


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5001, debug=True)
