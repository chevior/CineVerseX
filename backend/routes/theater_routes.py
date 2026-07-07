from flask import Blueprint, render_template, request, redirect, url_for
from auth.guards import admin_required
from extensions import db
from models.theater import Theater, Screen
from services.activity_service import log_activity

theater_bp = Blueprint("theater_bp", __name__)

AMENITY_SETS = [
    ["IMAX", "Dolby Atmos", "Recliner", "Cafe"],
    ["4K Projection", "Dolby 7.1", "Premium Seats", "Parking"],
    ["Laser Projection", "Family Lounge", "Food Court", "Online Entry"],
    ["XL Screen", "Couple Seats", "Wheelchair Access", "Cafe"],
]


def split_amenities(theater, fallback_index=0):
    if theater.amenities:
        return [item.strip() for item in theater.amenities.split(",") if item.strip()]

    return AMENITY_SETS[fallback_index % len(AMENITY_SETS)]


def pagination_window(current_page, total_pages, radius=2):
    if total_pages <= 1:
        return []

    current_page = max(1, min(current_page, total_pages))
    pages = {1, total_pages}

    for page_number in range(current_page - radius, current_page + radius + 1):
        if 1 <= page_number <= total_pages:
            pages.add(page_number)

    ordered_pages = sorted(pages)
    window = []
    previous = None

    for page_number in ordered_pages:
        if previous is not None and page_number - previous > 1:
            window.append(None)

        window.append(page_number)
        previous = page_number

    return window


def clean_location_text(value):
    text = value or ""

    for old, new in (
        ("Bengaluru Urban/Rural", ""),
        ("Bengaluru Urban", ""),
        ("Bengaluru Rural", ""),
        ("Bengaluru region", ""),
        ("Bengaluru", ""),
        ("Bangalore", ""),
        ("Karnataka", ""),
    ):
        text = text.replace(old, new)

    while ", ," in text:
        text = text.replace(", ,", ",")

    return " ".join(text.strip(" ,").split())


@theater_bp.route("/theaters")
def theaters():
    selected_format = request.args.get("format", "")
    selected_area = request.args.get("area", "")
    selected_city = request.args.get("city", "")
    selected_page = max(request.args.get("page", 1, type=int), 1)
    per_page = 30
    query_text = request.args.get("q", "").strip()
    all_theaters = Theater.query.filter(Theater.name != "BookMyShow")\
        .order_by(Theater.city.asc(), Theater.name.asc()).all()
    theater_cards = []
    all_areas = []
    all_cities = []

    for index, theater in enumerate(all_theaters):
        seats = sum((screen.total_seats or 0) for screen in theater.screens)
        display_name = clean_location_text(theater.name)
        address_display = clean_location_text(theater.address)
        area = clean_location_text((theater.address or theater.city).split(",")[0]).strip()
        city_display = clean_location_text(theater.city)
        theater_format = "Multiplex" if (theater.total_screens or 0) >= 3 else "Single Screen"
        linked_titles = []

        if area and area not in all_areas:
            all_areas.append(area)

        if city_display and city_display not in all_cities:
            all_cities.append(city_display)

        if selected_city and selected_city != city_display:
            continue

        if selected_format and selected_format != theater_format:
            continue

        if selected_area and selected_area != area:
            continue

        if query_text:
            haystack = f"{theater.name} {theater.city} {theater.address} {address_display}".lower()

            if query_text.lower() not in haystack:
                continue

        for show in theater.shows:
            if show.movie and show.movie.title not in linked_titles:
                linked_titles.append(show.movie.title)

        theater_cards.append({
            "theater": theater,
            "display_name": display_name,
            "seats": seats,
            "screens": sorted(theater.screens, key=lambda screen: screen.screen_name or ""),
            "linked_titles": linked_titles[:4],
            "amenities": split_amenities(theater, index),
            "area": area,
            "city": city_display,
            "address_display": address_display,
            "map_query": theater.map_url or f"https://www.google.com/maps/search/?api=1&query={(display_name + ' ' + address_display).strip()}",
            "format": theater_format,
        })

    total_theaters = len(theater_cards)
    total_pages = max((total_theaters + per_page - 1) // per_page, 1)
    selected_page = min(selected_page, total_pages)
    start_index = (selected_page - 1) * per_page
    paged_theater_cards = theater_cards[start_index:start_index + per_page]

    summary = {
        "venues": total_theaters,
        "screens": sum(card["theater"].total_screens or 0 for card in theater_cards),
        "seats": sum(card["seats"] for card in theater_cards),
        "multiplex": sum(1 for card in theater_cards if card["format"] == "Multiplex"),
        "single_screen": sum(1 for card in theater_cards if card["format"] == "Single Screen"),
        "cities": len(all_cities),
    }

    return render_template(
        "theaters.html",
        theater_cards=paged_theater_cards,
        summary=summary,
        areas=sorted(all_areas),
        cities=sorted(all_cities),
        selected_format=selected_format,
        selected_area=selected_area,
        selected_city=selected_city,
        selected_page=selected_page,
        total_pages=total_pages,
        pagination_pages=pagination_window(selected_page, total_pages),
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
            total_screens=int(request.form["total_screens"] or 1),
            amenities=request.form.get("amenities", "").strip(),
            parking_info=request.form.get("parking_info", "").strip(),
            food_available="food_available" in request.form,
            map_url=request.form.get("map_url", "").strip(),
        )

        db.session.add(theater)
        db.session.commit()
        log_activity("Theater Added", f"Added theater: {theater.name}", notify=True)

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
            total_seats=int(request.form["total_seats"]),
            vip_seats=int(request.form.get("vip_seats") or 0),
            premium_seats=int(request.form.get("premium_seats") or 0),
            standard_seats=int(request.form.get("standard_seats") or 0),
            couple_seats=int(request.form.get("couple_seats") or 0),
            wheelchair_seats=int(request.form.get("wheelchair_seats") or 0),
        )

        db.session.add(screen)
        db.session.commit()
        log_activity("Screen Added", f"Added screen: {screen.screen_name}", notify=True)

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


@theater_bp.route("/theater/<int:theater_id>")
def theater_details(theater_id):
    theater = Theater.query.get_or_404(theater_id)
    nearby_theaters = Theater.query.filter(
        Theater.id != theater.id,
        Theater.city == theater.city
    ).order_by(Theater.name.asc()).limit(6).all()

    return render_template(
        "theater_details.html",
        theater=theater,
        amenities=split_amenities(theater),
        nearby_theaters=nearby_theaters,
        map_url=theater.map_url or f"https://www.google.com/maps/search/?api=1&query={theater.name} {theater.city}",
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
        theater.amenities = request.form.get("amenities", "").strip()
        theater.parking_info = request.form.get("parking_info", "").strip()
        theater.food_available = "food_available" in request.form
        theater.map_url = request.form.get("map_url", "").strip()

        db.session.commit()
        log_activity("Theater Edited", f"Edited theater: {theater.name}", notify=True)

        return redirect("/theaters")

    return render_template(
        "edit_theater.html",
        theater=theater
    )
@theater_bp.route("/delete-theater/<int:theater_id>")
@admin_required
def delete_theater(theater_id):

    theater = Theater.query.get_or_404(theater_id)
    name = theater.name

    db.session.delete(theater)
    db.session.commit()
    log_activity("Theater Deleted", f"Deleted theater: {name}", notify=True)

    return redirect("/theaters")
