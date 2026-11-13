"""Flask-WTF forms. Every form carries a CSRF token and validates on the server."""
from flask_wtf import FlaskForm
from wtforms import PasswordField, SelectChoice, SelectField, StringField, TextAreaField
from wtforms.validators import (
    URL,
    DataRequired,
    Email,
    EqualTo,
    Length,
    Optional,
    Regexp,
    ValidationError,
)

from .models import SEVERITIES, User


class LoginForm(FlaskForm):
    username = StringField("Username", validators=[DataRequired()])
    password = PasswordField("Password", validators=[DataRequired()])


class RegisterForm(FlaskForm):
    username = StringField(
        "Username",
        validators=[
            DataRequired(),
            Length(min=3, max=64),
            Regexp(
                r"^[A-Za-z0-9_.-]+$",
                message="Letters, numbers, dot, dash and underscore only.",
            ),
        ],
    )
    email = StringField("Email", validators=[DataRequired(), Email(), Length(max=120)])
    password = PasswordField(
        "Password",
        validators=[DataRequired(), Length(min=8, message="Use at least 8 characters.")],
    )
    confirm = PasswordField(
        "Confirm password",
        validators=[DataRequired(), EqualTo("password", message="Passwords do not match.")],
    )

    def validate_username(self, field):
        if User.find_by_username(field.data):
            raise ValidationError("That username is taken.")

    def validate_email(self, field):
        if User.query.filter_by(email=field.data.lower()).first():
            raise ValidationError("An account with that email already exists.")


class ServiceForm(FlaskForm):
    name = StringField(
        "Name",
        validators=[
            DataRequired(),
            Length(max=80),
            Regexp(r"^[a-z0-9][a-z0-9-]*$", message="Lowercase letters, numbers and dashes only."),
        ],
    )
    description = StringField("Description", validators=[Optional(), Length(max=255)])
    # require_tld=False so http://localhost:8000/health is accepted.
    repo_url = StringField(
        "Repository URL", validators=[Optional(), URL(require_tld=False), Length(max=255)]
    )
    health_url = StringField(
        "Health check URL", validators=[Optional(), URL(require_tld=False), Length(max=255)]
    )


class IncidentForm(FlaskForm):
    title = StringField("Title", validators=[DataRequired(), Length(max=200)])
    service_id = SelectField("Service", coerce=int, validators=[DataRequired()])
    # 0 means "not linked to a deployment".
    deployment_id = SelectField("Linked deployment", coerce=int, default=0)
    severity = SelectField(
        "Severity", choices=[SelectChoice(s, s.capitalize()) for s in SEVERITIES], default="MEDIUM"
    )
    root_cause = TextAreaField("Root cause", validators=[Optional(), Length(max=5000)])
