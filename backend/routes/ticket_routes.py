from flask import Blueprint, render_template, session, redirect, url_for

from models.ticket import Ticket
import os

from flask import send_file, current_app
from reportlab.pdfgen import canvas

ticket_bp = Blueprint("ticket_bp", __name__)


@ticket_bp.route("/my-tickets")
def my_tickets():

    if "user_id" not in session:
        return redirect(url_for("auth_bp.login"))

    tickets = Ticket.query.filter_by(
        user_id=session["user_id"]
    ).all()

    return render_template(
        "my_tickets.html",
        tickets=tickets
    )
@ticket_bp.route("/download-ticket/<int:ticket_id>")
def download_ticket(ticket_id):

    if "user_id" not in session:
        return redirect(url_for("auth_bp.login"))

    ticket = Ticket.query.get_or_404(ticket_id)

    pdf_folder = os.path.join(
        current_app.root_path,
        "static",
        "tickets"
    )

    os.makedirs(pdf_folder, exist_ok=True)

    pdf_path = os.path.join(
        pdf_folder,
        f"ticket_{ticket.id}.pdf"
    )

    c = canvas.Canvas(pdf_path)

    c.setFont("Helvetica-Bold", 20)
    c.drawString(180, 800, "CineVerse X Ticket")

    c.setFont("Helvetica", 14)
    c.drawString(100, 740, f"Ticket ID: {ticket.id}")
    c.drawString(100, 710, f"Movie: {ticket.movie_name}")
    c.drawString(100, 680, f"Theatre: {ticket.theatre_name}")
    c.drawString(100, 650, f"Show Time: {ticket.show_time}")
    c.drawString(100, 620, f"Seats: {ticket.seat_numbers}")
    c.drawString(100, 590, f"Amount: Rs. {ticket.total_amount}")
    c.drawString(100, 560, f"Status: {ticket.status}")

    c.save()

    return send_file(
        pdf_path,
        as_attachment=True
    )