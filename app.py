import os
import logging
import threading
from flask import Flask, render_template, request, redirect, url_for, jsonify, flash
from config import Config
from database import (
    init_db, get_listings, get_listings_count, get_all_settings,
    update_settings, get_runs, get_analysis, get_run_listings,
)
from scheduler import init_scheduler, update_schedule, get_next_run_time, scrape_job

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.secret_key = Config.FLASK_SECRET_KEY

# Initialize database
init_db()

# Initialize scheduler (guard against double-start in debug mode)
if os.environ.get("WERKZEUG_RUN_MAIN") == "true" or not app.debug:
    init_scheduler()


@app.route("/")
def dashboard():
    filters = {
        "min_price": request.args.get("min_price", type=int),
        "max_price": request.args.get("max_price", type=int),
        "bedrooms": request.args.get("bedrooms", type=int),
    }
    sort = request.args.get("sort", "first_seen_at")
    order = request.args.get("order", "DESC")
    page = request.args.get("page", 1, type=int)
    per_page = 50

    listings = get_listings(filters=filters, sort=sort, order=order, limit=per_page, offset=(page - 1) * per_page)
    total = get_listings_count(filters=filters)
    total_pages = max(1, (total + per_page - 1) // per_page)

    runs = get_runs(limit=1)
    last_run = runs[0] if runs else None
    next_run = get_next_run_time()

    return render_template(
        "dashboard.html",
        listings=listings,
        filters=filters,
        sort=sort,
        order=order,
        page=page,
        per_page=per_page,
        total=total,
        total_pages=total_pages,
        last_run=last_run,
        next_run=next_run,
    )


@app.route("/settings", methods=["GET"])
def settings_page():
    settings = get_all_settings()
    next_run = get_next_run_time()
    return render_template("settings.html", settings=settings, next_run=next_run)


@app.route("/settings", methods=["POST"])
def save_settings():
    try:
        new_settings = {
            "location_display_name": request.form.get("location_display_name", "London"),
            "location_identifier": request.form.get("location_identifier", "REGION%5E87490"),
            "min_price": int(request.form.get("min_price", 1300)),
            "max_price": int(request.form.get("max_price", 1750)),
            "min_bedrooms": int(request.form.get("min_bedrooms", 1)),
            "max_bedrooms": int(request.form.get("max_bedrooms", 1)),
            "property_type": request.form.get("property_type", "flat"),
            "radius": float(request.form.get("radius", 3.0)),
            "max_days_since_added": int(request.form.get("max_days_since_added", 1)),
            "include_let_agreed": "include_let_agreed" in request.form,
            "scheduler_hour": int(request.form.get("scheduler_hour", 5)),
            "scheduler_minute": int(request.form.get("scheduler_minute", 0)),
            "scheduler_enabled": "scheduler_enabled" in request.form,
        }

        # Validate
        if new_settings["min_price"] < 0 or new_settings["max_price"] < 0:
            flash("Price values must be positive", "error")
            return redirect(url_for("settings_page"))
        if new_settings["min_price"] > new_settings["max_price"]:
            flash("Min price cannot be greater than max price", "error")
            return redirect(url_for("settings_page"))
        if not (0 <= new_settings["scheduler_hour"] <= 23):
            flash("Hour must be between 0 and 23", "error")
            return redirect(url_for("settings_page"))
        if not (0 <= new_settings["scheduler_minute"] <= 59):
            flash("Minute must be between 0 and 59", "error")
            return redirect(url_for("settings_page"))

        update_settings(new_settings)
        update_schedule(
            new_settings["scheduler_hour"],
            new_settings["scheduler_minute"],
            new_settings["scheduler_enabled"],
        )
        flash("Settings saved successfully", "success")

    except (ValueError, TypeError) as e:
        flash(f"Invalid input: {e}", "error")

    return redirect(url_for("settings_page"))


@app.route("/scrape", methods=["POST"])
def manual_scrape():
    thread = threading.Thread(target=scrape_job, daemon=True)
    thread.start()
    flash("Scrape job started. Refresh the page in a few minutes to see results.", "info")
    return redirect(url_for("dashboard"))


@app.route("/runs")
def runs_page():
    runs = get_runs(limit=50)
    return render_template("runs.html", runs=runs)


@app.route("/analysis/<int:run_id>")
def analysis_page(run_id):
    analysis = get_analysis(run_id)
    listings = get_run_listings(run_id)

    # Build lookup for ranked listings
    listings_map = {str(l["rightmove_id"]): l for l in listings}

    return render_template(
        "analysis.html",
        analysis=analysis,
        listings=listings,
        listings_map=listings_map,
        run_id=run_id,
    )


@app.route("/api/status")
def api_status():
    runs = get_runs(limit=1)
    return jsonify({
        "next_run": get_next_run_time(),
        "last_run": runs[0] if runs else None,
    })


if __name__ == "__main__":
    app.run(debug=True, port=5001)
