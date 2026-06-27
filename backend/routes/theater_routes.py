from flask import Blueprint, render_template, request, redirect, url_for
from auth.guards import admin_required
from extensions import db
from models.theater import Theater, Screen

theater_bp = Blueprint("theater_bp", __name__)

AMENITY_SETS = [
    ["IMAX", "Dolby Atmos", "Recliner", "Cafe"],
    ["4K Projection", "Dolby 7.1", "Premium Seats", "Parking"],
    ["Laser Projection", "Family Lounge", "Food Court", "Online Entry"],
    ["XL Screen", "Couple Seats", "Wheelchair Access", "Cafe"],
]


@theater_bp.route("/theaters")
def theaters():
    selected_region = request.args.get("region", "")
    selected_format = request.args.get("format", "")
    selected_area = request.args.get("area", "")
    query_text = request.args.get("q", "").strip()
    all_theaters = Theater.query.filter(Theater.name != "BookMyShow")\
        .order_by(Theater.city.asc(), Theater.name.asc()).all()
    theater_cards = []
    all_areas = []

    for index, theater in enumerate(all_theaters):
        seats = sum((screen.total_seats or 0) for screen in theater.screens)
        area = (theater.address or theater.city).split(",")[0].strip()
        region = "Rural" if "Rural" in (theater.city or "") else "Urban"
        theater_format = "Multiplex" if (theater.total_screens or 0) >= 3 else "Single Screen"
        linked_titles = []

        if area and area not in all_areas:
            all_areas.append(area)

        if selected_region and selected_region != region:
            continue

        if selected_format and selected_format != theater_format:
            continue

        if selected_area and selected_area != area:
            continue

        if query_text:
            haystack = f"{theater.name} {theater.city} {theater.address}".lower()

            if query_text.lower() not in haystack:
                continue

        for show in theater.shows:
            if show.movie and show.movie.title not in linked_titles:
                linked_titles.append(show.movie.title)

        theater_cards.append({
            "theater": theater,
            "seats": seats,
            "screens": sorted(theater.screens, key=lambda screen: screen.screen_name or ""),
            "linked_titles": linked_titles[:4],
            "amenities": AMENITY_SETS[index % len(AMENITY_SETS)],
            "area": area,
            "region": region,
            "format": theater_format,
        })

    summary = {
        "venues": len(theater_cards),
        "screens": sum(card["theater"].total_screens or 0 for card in theater_cards),
        "seats": sum(card["seats"] for card in theater_cards),
        "urban": sum(1 for card in theater_cards if "Rural" not in (card["theater"].city or "")),
        "rural": sum(1 for card in theater_cards if "Rural" in (card["theater"].city or "")),
    }

    return render_template(
        "theaters.html",
        theater_cards=theater_cards,
        summary=summary,
        areas=sorted(all_areas),
        selected_region=selected_region,
        selected_format=selected_format,
        selected_area=selected_area,
        query_text=query_text
    )


@theater_bp.route("/add-theater", methods=["GET", "POST"])
@admin_required
def add_theater():

    if request.method == "POST":

        existing_theater = Theater.query.filter_by(
            name=request.form["name"],
            city=request.form["city"]
        ).first()

        if existing_theater:
            return "Theater already exists"

        theater = Theater(
            name=request.form["name"],
            city=request.form["city"],
            address=request.form["address"],
            total_screens=int(request.form["total_screens"] or 1)
        )

        db.session.add(theater)
        db.session.commit()

        return redirect(url_for("theater_bp.theaters"))

    return render_template("add_theater.html")


@theater_bp.route("/add-screen", methods=["GET", "POST"])
@admin_required
def add_screen():

    if request.method == "POST":

        existing_screen = Screen.query.filter_by(
            theater_id=int(request.form["theater_id"]),
            screen_name=request.form["screen_name"]
        ).first()

        if existing_screen:
            return "Screen already exists"

        screen = Screen(
            theater_id=int(request.form["theater_id"]),
            screen_name=request.form["screen_name"],
            total_seats=int(request.form["total_seats"])
        )

        db.session.add(screen)
        db.session.commit()

        return redirect(url_for("theater_bp.screens"))

    theaters = Theater.query.all()

    return render_template(
        "add_screen.html",
        theaters=theaters
    )

@theater_bp.route("/screens")
def screens():
    all_screens = Screen.query.all()

    return render_template(
        "screens.html",
        screens=all_screens
    )
@theater_bp.route("/edit-theater/<int:theater_id>",
                  methods=["GET","POST"])
@admin_required
def edit_theater(theater_id):

    theater = Theater.query.get_or_404(theater_id)

    if request.method == "POST":

        theater.name = request.form["name"]
        theater.city = request.form["city"]
        theater.address = request.form["address"]
        theater.total_screens = int(request.form["total_screens"] or 1)

        db.session.commit()

        return redirect("/theaters")

    return render_template(
        "edit_theater.html",
        theater=theater
    )
@theater_bp.route("/delete-theater/<int:theater_id>")
@admin_required
def delete_theater(theater_id):

    theater = Theater.query.get_or_404(theater_id)

    db.session.delete(theater)
    db.session.commit()

    return redirect("/theaters")
