import logging
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

logger = logging.getLogger(__name__)

scheduler = BackgroundScheduler()


def scrape_job():
    """The scheduled job that runs the full scrape -> analyze -> notify pipeline."""
    from database import (
        get_all_settings, create_scrape_run, upsert_listing,
        link_run_listing, complete_scrape_run, save_analysis, get_run_listings,
    )
    from scraper import run_scrape
    from analyzer import analyze_listings
    from notifier import send_telegram_message, format_analysis_message

    logger.info("Starting scheduled scrape job")
    settings = get_all_settings()
    run_id = create_scrape_run(settings)

    try:
        result = run_scrape(settings)
        new_count = 0

        for prop in result["properties"]:
            listing_id, is_new = upsert_listing(prop)
            link_run_listing(run_id, listing_id, is_new)
            if is_new:
                new_count += 1

        # Run Claude analysis if we have listings
        if result["properties"]:
            analysis = analyze_listings(result["properties"])
            if analysis:
                save_analysis(
                    run_id=run_id,
                    model=analysis["model"],
                    prompt=analysis["prompt"],
                    response=analysis["raw_response"],
                    ranked=analysis["rankings"],
                    tokens=analysis["tokens_used"],
                )
                # Send Telegram notification
                run_listings = get_run_listings(run_id)
                msg = format_analysis_message(analysis, run_listings)
                send_telegram_message(msg)
            else:
                logger.warning("Analysis returned None, skipping Telegram notification")
        else:
            logger.info("No properties found in this run")

        complete_scrape_run(run_id, "completed", len(result["properties"]), new_count)
        logger.info(f"Scrape job completed: {len(result['properties'])} found, {new_count} new")

    except Exception as e:
        logger.exception(f"Scrape job failed: {e}")
        complete_scrape_run(run_id, "failed", 0, 0, str(e))


def init_scheduler():
    """Initialize the scheduler with current DB settings."""
    from database import get_all_settings

    settings = get_all_settings()
    enabled = settings.get("scheduler_enabled", True)

    if enabled:
        hour = int(settings.get("scheduler_hour", 5))
        minute = int(settings.get("scheduler_minute", 0))
        trigger = CronTrigger(hour=hour, minute=minute)
        scheduler.add_job(
            scrape_job,
            trigger=trigger,
            id="daily_scrape",
            replace_existing=True,
            misfire_grace_time=3600,
        )
        logger.info(f"Scheduler initialized: daily at {hour:02d}:{minute:02d}")
    else:
        logger.info("Scheduler is disabled")

    scheduler.start()


def update_schedule(hour, minute, enabled):
    """Update the scheduler job dynamically."""
    try:
        scheduler.remove_job("daily_scrape")
    except Exception:
        pass

    if enabled:
        trigger = CronTrigger(hour=hour, minute=minute)
        scheduler.add_job(
            scrape_job,
            trigger=trigger,
            id="daily_scrape",
            replace_existing=True,
            misfire_grace_time=3600,
        )
        logger.info(f"Schedule updated: daily at {hour:02d}:{minute:02d}")
    else:
        logger.info("Scheduler disabled")


def get_next_run_time():
    """Return the next scheduled run time as a formatted string, or None."""
    job = scheduler.get_job("daily_scrape")
    if job and job.next_run_time:
        return job.next_run_time.strftime("%Y-%m-%d %H:%M:%S")
    return None
