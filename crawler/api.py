import logging
from flask import Flask, request, jsonify
from crawler import crawl_overview_page, crawl_single_article
from scheduler import CrawlerScheduler

# logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# init scheduler
scheduler = CrawlerScheduler()


@app.route('/health', methods=['GET'])
def health_check():
    """ health check """
    return jsonify({'status': 'healthy'})


@app.route('/internal/crawl/overview', methods=['POST'])
def trigger_overview_crawl():
    """ trigger a crawl of the overview page """
    try:
        new_articles = crawl_overview_page()
        return jsonify({
            'status': 'success',
            'message': f'Crawl completed successfully. Found {new_articles} new article versions.'
        })
    except Exception as e:
        logger.error(f'Error in overview crawl: {e}')
        return jsonify({
            'status': 'error',
            'message': f'Error during crawl: {str(e)}'
        }), 500


@app.route('/internal/crawl/article', methods=['POST'])
def trigger_article_crawl():
    """ trigger a crawl of a specific article """
    data = request.json
    if not data or 'url' not in data:
        return jsonify({
            'status': 'error',
            'message': 'Missing url'
        }), 400

    url = data['url']
    try:
        success = crawl_single_article(url)
        if success:
            return jsonify({
                'status': 'success',
                'message': f'Article {url} crawled successfully'
            })
        else:
            return jsonify({
                'status': 'warning',
                'message': f'Article {url} crawled but no new version was created'
            })
    except Exception as e:
        logger.error(f'Error in article crawl: {e}')
        return jsonify({
            'status': 'error',
            'message': f'Error during article crawl: {str(e)}'
        }), 500


@app.route('/internal/update-schedule', methods=['POST'])
def update_schedule():
    """ update the crawler schedule """
    data = request.json
    if not data or 'hours' not in data:
        return jsonify({
            'status': 'error',
            'message': 'Missing required param: hours'
        }), 400

    try:
        hours = int(data['hours'])
        if hours < 1:
            return jsonify({
                'status': 'error',
                'message': 'Schedule interval must be at least 1 hour'
            }), 400

        scheduler.update_schedule(hours=hours)

        return jsonify({
            'status': 'success',
            'message': f'Schedule updated to run every {hours} hours'
        })
    except ValueError:
        return jsonify({
            'status': 'error',
            'message': 'Hours param must be an int'
        }), 400
    except Exception as e:
        logger.error(f'Error updating schedule: {e}')
        return jsonify({
            'status': 'error',
            'message': f'Error updating schedule: {str(e)}'
        }), 500


@app.route('/internal/enable', methods=['POST'])
def enable_schedule():
    """ enable the crawler schedule """
    try:
        scheduler.update_schedule(enabled=True)

        return jsonify({
            'status': 'success',
            'message': 'Crawler schedule enabled'
        })
    except Exception as e:
        logger.error(f'Error enabling schedule: {e}')
        return jsonify({
            'status': 'error',
            'message': f'Error enabling schedule: {str(e)}'
        }), 500


@app.route('/internal/disable', methods=['POST'])
def disable_schedule():
    """ disable the crawler schedule """
    try:
        scheduler.update_schedule(enabled=False)

        return jsonify({
            'status': 'success',
            'message': 'Crawler schedule disabled'
        })
    except Exception as e:
        logger.error(f'Error disabling schedule: {e}')
        return jsonify({
            'status': 'error',
            'message': f'Error disabling schedule: {str(e)}'
        }), 500


if __name__ == '__main__':
    scheduler.start()

    try:
        app.run(host='0.0.0.0', port=8000)
    finally:
        scheduler.stop()
