from django import forms

from . import avatars
from .models import LOCALE_CHOICES, AuthSource, DateStyle, Theme
from .prefs import time_zone_choices


class ProfileForm(forms.Form):
    first_name = forms.CharField(max_length=150, required=False)
    last_name = forms.CharField(max_length=150, required=False)
    email = forms.EmailField(required=False)
    theme = forms.ChoiceField(choices=Theme.choices)
    locale = forms.ChoiceField(
        choices=[("", "Instance default")] + LOCALE_CHOICES,
        required=False,
        help_text="How dates and times are written. The interface stays in English.",
    )
    date_style = forms.ChoiceField(choices=DateStyle.choices)
    time_zone = forms.ChoiceField(
        choices=[("", "Instance default")] + time_zone_choices(), required=False
    )
    avatar = forms.FileField(
        required=False, widget=forms.ClearableFileInput(attrs={"accept": "image/*"})
    )
    remove_avatar = forms.BooleanField(required=False)

    IDENTITY_FIELDS = ("first_name", "last_name", "email")

    def __init__(self, *args, user, profile, **kwargs):
        self.user = user
        self.profile = profile
        initial = {f: getattr(user, f) for f in self.IDENTITY_FIELDS}
        initial.update(
            theme=profile.theme,
            locale=profile.locale,
            date_style=profile.date_style,
            time_zone=profile.time_zone,
        )
        super().__init__(*args, initial=initial, **kwargs)
        self.identity_editable = user.auth_source == AuthSource.LOCAL
        if not self.identity_editable:
            for name in self.IDENTITY_FIELDS:
                self.fields[name].disabled = True
        self.uploads_enabled = avatars.uploads_enabled()
        if not self.uploads_enabled:
            del self.fields["avatar"]
            del self.fields["remove_avatar"]

    def clean_avatar(self):
        upload = self.cleaned_data.get("avatar")
        if upload:
            try:
                avatars.process_avatar(upload)
            except avatars.AvatarError as exc:
                raise forms.ValidationError(str(exc)) from exc
            upload.seek(0)
        return upload

    def save(self):
        user, profile = self.user, self.profile
        data = self.cleaned_data
        if self.identity_editable:
            for name in self.IDENTITY_FIELDS:
                setattr(user, name, data[name])
            user.save(update_fields=list(self.IDENTITY_FIELDS))
        for name in ("theme", "locale", "date_style", "time_zone"):
            setattr(profile, name, data[name])
        profile.save(update_fields=["theme", "locale", "date_style", "time_zone"])
        if self.uploads_enabled:
            if data.get("avatar"):
                avatars.set_avatar(profile, data["avatar"])
            elif data.get("remove_avatar"):
                avatars.clear_avatar(profile)
