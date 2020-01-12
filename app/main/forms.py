from flask_wtf import FlaskForm

from wtforms import StringField, SubmitField
from wtforms.validators import DataRequired, Length


class OTPForm(FlaskForm):
    otp = StringField('OTP', validators=[DataRequired(), Length(1, 7)])
    submit = SubmitField('submit')


class SecretForm(FlaskForm):
    submit = SubmitField("""Delete from server""")


class InitForm(FlaskForm):
    submit = SubmitField("""Initialize""")
