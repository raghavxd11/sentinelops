"""Login, register and logout."""
from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required, login_user, logout_user

from ..extensions import db
from ..forms import LoginForm, RegisterForm
from ..models import User

bp = Blueprint("auth", __name__)


def is_safe_next(target):
    """Only allow redirects to a path on this site (blocks open redirects)."""
    return bool(target) and target.startswith("/") and not target.startswith(("//", "/\\"))


@bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("main.overview"))

    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(username=form.username.data.strip()).first()
        if user and user.check_password(form.password.data):
            login_user(user)
            target = request.args.get("next")
            return redirect(target if is_safe_next(target) else url_for("main.overview"))
        # Same message for both cases so the form does not reveal which usernames exist.
        form.password.errors.append("Wrong username or password.")
    return render_template("auth/login.html", form=form)


@bp.route("/register", methods=["GET", "POST"])
def register():
    if current_user.is_authenticated:
        return redirect(url_for("main.overview"))

    form = RegisterForm()
    if form.validate_on_submit():
        user = User(username=form.username.data, email=form.email.data.lower())
        user.set_password(form.password.data)
        db.session.add(user)
        db.session.commit()
        login_user(user)
        flash(f"Account {user.username} created.", "success")
        return redirect(url_for("main.overview"))
    return render_template("auth/register.html", form=form)


@bp.route("/logout", methods=["POST"])
@login_required
def logout():
    logout_user()
    flash("Signed out.", "info")
    return redirect(url_for("main.landing"))
