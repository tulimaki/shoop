# -*- coding: utf-8 -*-
# This file is part of Shuup.
#
# Copyright (c) 2012-2018, Shuup Inc. All rights reserved.
#
# This source code is licensed under the OSL-3.0 license found in the
# LICENSE file in the root directory of this source tree.
from __future__ import unicode_literals

import datetime

from django import forms
from django.contrib import messages
from django.core.urlresolvers import reverse_lazy
from django.db import transaction
from django.http import HttpResponseRedirect
from django.utils.encoding import force_text
from django.utils.translation import ugettext_lazy as _
from django.views.generic import DetailView

from shuup.admin.forms.fields import Select2MultipleField, WeekdayField
from shuup.admin.forms.widgets import TimeInput
from shuup.admin.shop_provider import get_shop
from shuup.admin.toolbar import get_default_edit_toolbar
from shuup.admin.utils.picotable import Column, TextFilter
from shuup.admin.utils.views import CreateOrUpdateView, PicotableListView
from shuup.core.models import Shop
from shuup.discounts.models import Discount, HappyHour, TimeRange


class HappyHourListView(PicotableListView):
    model = HappyHour
    url_identifier = "discounts_happy_hour"

    default_columns = [
        Column(
            "name", _("Happy Hour Name"), sort_field="name", display="name",
            filter_config=TextFilter(filter_field="name", placeholder=_("Filter by name..."))
        )
    ]

    def get_queryset(self):
        return HappyHour.objects.filter(shops=get_shop(self.request))


def _get_initial_data_for_time_ranges(happy_hour):
    weekdays = []
    from_hour = None
    to_hour = None
    for time_range in happy_hour.time_ranges.all().order_by("weekday", "from_hour"):
        if from_hour is None:
            from_hour = time_range.from_hour

        if to_hour is None:
            to_hour = time_range.to_hour
        elif time_range.to_hour < to_hour:
            to_hour = time_range.to_hour

        if not time_range.parent and time_range.weekday not in weekdays:
            weekdays.append(time_range.weekday)

    return weekdays, from_hour, to_hour


def _create_time_ranges_from_data(happy_hour, weekdays, from_hour, to_hour):
    for weekday in weekdays.split(","):
        if to_hour < from_hour:
            matching_day = int(weekday)
            tomorrow = (matching_day + 1 if matching_day < 6 else 0)
            parent = TimeRange.objects.create(
                happy_hour=happy_hour, from_hour=from_hour, to_hour=datetime.time(hour=23),
                weekday=matching_day)
            TimeRange.objects.create(
                happy_hour=happy_hour, parent=parent, from_hour=datetime.time(hour=0), to_hour=to_hour,
                weekday=tomorrow)
        else:
            TimeRange.objects.create(
                happy_hour=happy_hour, from_hour=from_hour, to_hour=to_hour, weekday=int(weekday))


class HappyHourForm(forms.ModelForm):
    weekdays = WeekdayField()
    from_hour = forms.TimeField()
    to_hour = forms.TimeField()

    class Meta:
        model = HappyHour
        exclude = ()

    def __init__(self, *args, **kwargs):
        self.request = kwargs.pop("request")
        self.shop = get_shop(self.request)
        super(HappyHourForm, self).__init__(*args, **kwargs)

        if self.instance.pk:
            self.fields["discounts"] = Select2MultipleField(
                label=_("Product Discounts"),
                help_text=_("Select discounts for this happy hour."),
                model=Discount,
                required=False
            )
            initial_discounts = (self.instance.discounts.all() if self.instance.pk else [])
            self.fields["discounts"].initial = initial_discounts
            self.fields["discounts"].widget.choices = [
                (discount.pk, force_text(discount)) for discount in initial_discounts
            ]

        if self.instance.pk:
            weekdays, from_hour, to_hour = _get_initial_data_for_time_ranges(self.instance)
            if weekdays and from_hour and to_hour:
                self.fields["weekdays"].initial = weekdays
                self.fields["from_hour"].initial = from_hour
                self.fields["to_hour"].initial = to_hour

        # Since we touch these views in init we need to reset some
        # widgets and help texts after setting the initial values.
        self.fields["from_hour"].widget = TimeInput()
        self.fields["to_hour"].widget = TimeInput()
        help_texts = [
            ("from_hour", _("12pm is considered noon and 12am as midnight.")),
            ("to_hour", _("12pm is considered noon and 12am as midnight. End time is considered match.")),
            ("weekdays", _("Weekdays the happy hour is active."))
        ]
        for field, help_text in help_texts:
            self.fields[field].help_text = help_text

        # add shops field when superuser only
        if getattr(self.request.user, "is_superuser", False):
            self.fields["shops"] = Select2MultipleField(
                label=_("Shops"),
                help_text=_("Select shops for this discount. Keep it blank to share with all shops."),
                model=Shop,
                required=False
            )
            initial_shops = (self.instance.shops.all() if self.instance.pk else [])
            self.fields["shops"].widget.choices = [(shop.pk, force_text(shop)) for shop in initial_shops]
        else:
            # drop shops fields
            self.fields.pop("shops", None)

    def save(self, commit=True):
        instance = super(HappyHourForm, self).save(commit)
        if "shops" not in self.fields:
            instance.shops = [self.shop]

        data = self.cleaned_data
        if "discounts" in self.fields:
            instance.discounts = data.get("discounts", [])

        with transaction.atomic():
            instance.time_ranges.all().delete()

            weekdays = data.get("weekdays", "")
            from_hour = data.get("from_hour")
            to_hour = data.get("to_hour")
            if not (weekdays and from_hour and to_hour):
                return instance

            _create_time_ranges_from_data(instance, weekdays, from_hour, to_hour)

        return instance


class HappyHourEditView(CreateOrUpdateView):
    model = HappyHour
    form_class = HappyHourForm
    template_name = "shuup/discounts/edit.jinja"
    context_object_name = "discounts"

    def get_queryset(self):
        if getattr(self.request.user, "is_superuser", False):
            return HappyHour.objects.all()

        return HappyHour.objects.filter(shops=get_shop(self.request))

    def get_toolbar(self):
        save_form_id = self.get_save_form_id()
        if save_form_id:
            object = self.get_object()
            delete_url = (
                reverse_lazy("shuup_admin:discounts_happy_hour.delete", kwargs={"pk": object.pk})
                if object.pk else None)
            return get_default_edit_toolbar(self, save_form_id, delete_url=delete_url)

    def get_form_kwargs(self):
        kwargs = super(HappyHourEditView, self).get_form_kwargs()
        kwargs["request"] = self.request
        return kwargs


class HappyHourDeleteView(DetailView):
    model = HappyHour

    def get_queryset(self):
        return HappyHour.objects.filter(shops=get_shop(self.request))

    def post(self, request, *args, **kwargs):
        happy_hour = self.get_object()
        happy_hour.delete()
        messages.success(request, _("%s has been deleted.") % happy_hour)
        return HttpResponseRedirect(reverse_lazy("shuup_admin:discounts_happy_hour.list"))
