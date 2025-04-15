import logging
import threading
import time
from crawler import get_db_connection, crawl_overview_page
from datetime import datetime, timedelta
from psycopg2.extras import DictCursor

# logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class CrawlerScheduler:
    def __init__(self):
        self.thread = None
        self.should_stop = False

    def get_crawler_config(self):
        """ get crawler config from db """
        conn = get_db_connection()
        try:
            with conn.cursor(cursor_factory=DictCursor) as cursor:
                cursor.execute('SELECT * FROM crawler_config WHERE id=1')
                config = dict(zip([desc[0] for desc in cursor.description], cursor.fetchone()))
                return config
        finally:
            conn.close()

    def update_next_run(self):
        """ update next tun time based on current config """
        config = self.get_crawler_config()

        if not config['is_enabled']:
            logger.info('Scheduled crawler not enabled')
            return False

        interval_hours = config['schedule_interval_hours']
        next_run = datetime.now() + timedelta(hours=interval_hours)

        conn = get_db_connection()
        try:
            with conn.cursor(cursor_factory=DictCursor) as cursor:
                cursor.execute('UPDATE crawler_config SET next_run = %s WHERE id = 1', (next_run,))
                conn.commit()
                logger.info(f'Next crawler run at {next_run}')
            return True
        except Exception as e:
            logger.error(f'Error updating next_run: {e}')
            return False
        finally:
            conn.close()

    def _scheduler_loop(self):
        """ main schedule loop """
        logger.info('Scheduler thread started')

        while not self.should_stop:
            try:
                config = self.get_crawler_config()

                if config['is_enabled']:
                    current_time = datetime.now()
                    next_run = config['next_run']

                    if next_run is None or current_time > next_run:
                        logger.info('Running scheduled crawl')
                        crawl_overview_page()
                        self.update_next_run()

                # sleep interval set to 20 minutes to balance database load, lower resource usage while still being responsive to schedule chnages
                time.sleep(1200)

            except Exception as e:
                logger.error(f'Error in main loop: {e}')
                time.sleep(1200)

        logger.info('Scheduler thread stopped')

    def start(self):
        """ start scheduler thread """
        if self.thread is None or not self.thread.is_alive():
            self.should_stop = False
            self.thread = threading.Thread(target=self._scheduler_loop, daemon=True)
            self.thread.start()
            logger.info('Scheduler started')

            # run crawl and update next run time
            self.update_next_run()

    def stop(self):
        """ stop scheduler thread """
        if self.thread and self.thread.is_alive():
            self.should_stop = True
            logger.info('Scheduler stopped')

    def update_schedule(self, hours=None, enabled=None):
        """ update schedule configuration """
        conn = get_db_connection()
        try:
            with conn.cursor(cursor_factory=DictCursor) as cursor:
                if hours is not None:
                    cursor.execute(
                        'UPDATE crawler_config SET schedule_interval_hours = %s WHERE id = 1',
                        (hours, )
                    )

                if enabled is not None:
                    cursor.execute(
                        'UPDATE crawler_config SET schedule_enabled = %s WHERE id = 1',
                        (enabled, )
                    )

                conn.commit()

            if self.thread and self.thread.is_alive():
                self.update_next_run()

            return True
        except Exception as e:
            conn.rollback()
            logger.error(f'Error updating schedule: {e}')
            return False
        finally:
            conn.close()
