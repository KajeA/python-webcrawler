import os
import logging
from http.client import responses

import psycopg2
import requests
from flask import Flask, request, jsonify
from psycopg2.extras import DictCursor

# logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

CRAWLER_SERVICE = os.environ.get('CRAWLER_SERVICE', 'crawler')
CRAWLER_PORT = os.environ.get('CRAWLER_PORT', '8000')

DB_HOST = os.environ.get('DB_HOST', 'postgres')
DB_PORT = os.environ.get('DB_PORT', '5432')
DB_NAME = os.environ.get('DB_NAME', 'tagesschau')
DB_USER = os.environ.get('DB_USER', 'postgres')
DB_PASSWORD = os.environ.get('DB_PASSWORD', 'postgres')

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
    """ health check """
    return jsonify({'status': 'healthy'})


@app.route('/api/config', methods=['GET'])
def get_crawler_config():
    """ get crawler configuration """
    conn = get_db_connection()
    try:
        with conn.cursor(cursor_factory=DictCursor) as cursor:
            cursor.execute('SELECT * FROM crawler_config WHERE id = 1')
            config = dict(cursor.fetchone())

            # convert datetime to string
            if config['last_run']:
                config['last_run'] = config['last_run'].isoformat()
            if config['next_run']:
                config['next_run'] = config['next_run'].isoformat()

            return jsonify(config)
    finally:
        conn.close()


@app.route('/api/config/schedule', methods=['PUT'])
def update_schedule():
    """ update crawler schedule """
    data = request.json
    if not data or 'hours' not in data:
        return jsonify({'status': 'error', 'message': 'missing required param: hours'}), 400

    hours = data['hours']
    try:
        hours = int(hours)
        if hours < 1:
            return jsonify({'status': 'error', 'message': 'schedule must be at least 1 hour'}), 400
    except ValueError:
        return jsonify({'status': 'error', 'message': 'hours param must be int'}), 400

    conn = get_db_connection()
    try:
        with conn.cursor(cursor_factory=DictCursor) as cursor:
            cursor.execute(
                'UPDATE crawler_config SET schedule_interval_hours = %s WHERE id = 1',
                (hours,)
            )
            conn.commit()

        try:
            requests.post(
                f'http://{CRAWLER_SERVICE}:{CRAWLER_PORT}/internal/update-schedule',
                json={'hours': hours},
                timeout=5
            )
        except requests.exceptions.RequestException as e:
            logger.warning(f'Failed to update schedule: {e}')

        return jsonify({
            'status': 'success',
            'message': f'Schedule updated to run every {hours} hours'
        })
    finally:
        conn.close()


@app.route('/api/config/schedule/increase', methods=['POST'])
def increase_schedule():
    """ increase crawler schedule """
    conn = get_db_connection()
    try:
        with conn.cursor(cursor_factory=DictCursor) as cursor:
            cursor.execute(
                """
                UPDATE crawler_config 
                SET schedule_interval_hours = schedule_interval_hours + 1 
                WHERE id = 1 RETURNING schedule_interval_hours
                """
            )
            new_hours = cursor.fetchone()[0]
            conn.commit()

        try:
            requests.post(
                f'http://{CRAWLER_SERVICE}:{CRAWLER_PORT}/internal/update-schedule',
                json={'hours': new_hours},
                timeout=5
            )
        except requests.RequestException as e:
            logger.warning(f'Failed to update schedule: {e}')

        return jsonify({
            'status': 'success',
            'message': f'Schedule increased to run every {new_hours} hours'
        })
    finally:
        conn.close()


@app.route('/api/config/schedule/decrease', methods=['POST'])
def decrease_schedule():
    """ decrease crawler schedule """
    conn = get_db_connection()
    try:
        with conn.cursor(cursor_factory=DictCursor) as cursor:
            cursor.execute(
                """
                UPDATE crawler_config 
                SET schedule_interval_hours = GREATEST(1, schedule_interval_hours - 1) 
                WHERE id = 1 RETURNING schedule_interval_hours
                """
            )
            new_hours = cursor.fetchone()[0]
            conn.commit()

        try:
            requests.post(
                f'http://{CRAWLER_SERVICE}:{CRAWLER_PORT}/internal/update-schedule',
                json={'hours': new_hours},
                timeout=5
            )
        except requests.RequestException as e:
            logger.warning(f'Failed to update schedule: {e}')

        return jsonify({
            'status': 'success',
            'message': f'Schedule decreased to run every {new_hours} hours'
        })
    finally:
        conn.close()


@app.route('/api/config/enable', methods=['POST'])
def enable_crawler():
    """ enable crawler """
    conn = get_db_connection()
    try:
        with conn.cursor(cursor_factory=DictCursor) as cursor:
            cursor.execute(
                'UPDATE crawler_config SET is_enabled = TRUE WHERE id = 1'
            )
            conn.commit()

        try:
            requests.post(
                f'http://{CRAWLER_SERVICE}:{CRAWLER_PORT}/internal/enable',
                timeout=5
            )
        except requests.RequestException as e:
            logger.warning(f'Failed to enable crawler: {e}')

        return jsonify({
            'status': 'success',
            'message': f'Crawler enabled successfully'
        })
    finally:
        conn.close()


@app.route('/api/config/disable', methods=['POST'])
def disable_crawler():
    """ disable crawler """
    conn = get_db_connection()
    try:
        with conn.cursor(cursor_factory=DictCursor) as cursor:
            cursor.execute(
                'UPDATE crawler_config SET is_enabled = FALSE WHERE id = 1'
            )
            conn.commit()

        try:
            requests.post(
                f'http://{CRAWLER_SERVICE}:{CRAWLER_PORT}/internal/disable',
                timeout=5
            )
        except requests.RequestException as e:
            logger.warning(f'Failed to disable crawler: {e}')

        return jsonify({
            'status': 'success',
            'message': f'Crawler disabled successfully'
        })
    finally:
        conn.close()


@app.route('/api/crawl/overview', methods=['POST'])
def trigger_overview_crawl():
    """ trigger crawl of overview page """
    try:
        response = requests.post(
            f'http://{CRAWLER_SERVICE}:{CRAWLER_PORT}/internal/crawl/overview',
            # crawling should finish within 5 minutes
            timeout=300
        )
        response.raise_for_status()
        return jsonify(response.json())
    except requests.RequestException as e:
        logger.error(f'Failed to trigger overview crawl: {e}')
        return jsonify({
            'status': 'error',
            'message': f'Failed to trigger overview crawl'
        }), 500


@app.route('/api/crawl/article', methods=['POST'])
def trigger_article_crawl():
    """ trigger crawl of article page """
    data = request.json()
    if not data or 'url' not in data:
        return jsonify({
            'status': 'error',
            'message': 'missing url'
        }), 400

    url = data['url']
    if not url.startswith('https://www.tagesschau.de'):
        return jsonify({
            'status': 'error',
            'message': 'invalid url'
        }), 400

    try:
        response = requests.post(
            f'http://{CRAWLER_SERVICE}:{CRAWLER_PORT}/internal/crawl/article',
            json={'url': url},
            timeout=5
        )
        response.raise_for_status()
        return jsonify(response.json())
    except requests.RequestException as e:
        logger.error(f'Failed to trigger article crawl: {e}')
        return jsonify({
            'status': 'error',
            'message': 'failed to trigger article crawl'
        }), 500


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
        'message': 'resource not found',
    }), 404


@app.errorhandler(500)
def handle_server_error(e):
    logger.error(f'Server error: {e}')
    return jsonify({
        'status': 'error',
        'message': 'Internal server error',
    }), 500


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
