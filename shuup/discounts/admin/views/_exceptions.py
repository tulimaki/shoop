# -*- coding: utf-8 -*-
# This file is part of Shuup.
#
# Copyright (c) 2012-2018, Shuup Inc. All rights reserved.
#
# This source code is licensed under the OSL-3.0 license found in the
# LICENSE file in the root directory of this source tree.
from __future__ import unicode_literals

from django import forms
from django.contrib import messages
from django.core.urlresolvers import reverse_lazy
from django.http import HttpResponseRedirect
from django.utils.encoding import force_text
from django.utils.translation import ugettext_lazy as _
from django.views.generic import DetailView

from shuup.admin.forms.fields import Select2MultipleField
from shuup.admin.shop_provider import get_shop
from shuup.admin.toolbar import get_default_edit_toolbar
from shuup.admin.utils.picotable import Column, DateRangeFilter, TextFilter
from shuup.admin.utils.views import CreateOrUpdateView, PicotableListView
from shuup.core.models import Shop
from shuup.discounts.models import AvailabilityException, Discount
from shuup.utils.i18n import get_locally_formatted_datetime


class AvailabilityExceptionListView(PicotableListView):
    model = AvailabilityException
    url_identifier = "discounts_availability_exception"

    default_columns = [
        Column(
            "name", _("Exception Name"), sort_field="name", display="name",
            filter_config=TextFilter(filter_field="name", placeholder=_("Filter by name..."))
        ),
        Column(
            "start_datetime", _("Start Date and Time"), display="format_start_datetime", filter_config=DateRangeFilter()
        ),
        Column(
            "end_datetime", _("End Date and Time"), display="format_end_datetime", filter_config=DateRangeFilter()
        )
    ]

    def get_queryset(self):
        return AvailabilityException.objects.filter(shops=get_shop(self.request))

    def format_start_datetime(self, instance, *args, **kwargs):
        return get_locally_formatted_datetime(instance.start_datetime) if instance.start_datetime else ""

    def format_end_datetime(self, instance, *args, **kwargs):
        return get_locally_formatted_datetime(instance.end_datetime) if instance.end_datetime else ""


class AvailabilityExceptionForm(forms.ModelForm):
    class Meta:
        model = AvailabilityException
        exclude = ()

    def __init__(self, *args, **kwargs):
        self.request = kwargs.pop("request")
        self.shop = get_shop(self.request)
        super(AvailabilityExceptionForm, self).__init__(*args, **kwargs)

        if self.instance.pk:
            self.fields["discounts"] = Select2MultipleField(
                label=_("Product Discounts"),
                help_text=_("Select discounts to be ignored on given time frame."),
                model=Discount,
                required=False
            )
            initial_discounts = (self.instance.discounts.all() if self.instance.pk else [])
            self.fields["discounts"].widget.choices = [
                (discount.pk, force_text(discount)) for discount in initial_discounts
            ]

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
        instance = super(AvailabilityExceptionForm, self).save(commit)
        if "shops" not in self.fields:
            instance.shops = [self.shop]

        if "discounts" in self.fields:
            data = self.cleaned_data
            instance.discounts = data.get("discounts", [])

        return instance


class AvailabilityExceptionEditView(CreateOrUpdateView):
    model = AvailabilityException
    form_class = AvailabilityExceptionForm
    template_name = "shuup/discounts/edit.jinja"
    context_object_name = "discounts"

    def get_queryset(self):
        if getattr(self.request.user, "is_superuser", False):
            return AvailabilityException.objects.all()

        return AvailabilityException.objects.filter(shops=get_shop(self.request))

    def get_toolbar(self):
        save_form_id = self.get_save_form_id()
        if save_form_id:
            object = self.get_object()
            delete_url = (
                reverse_lazy("shuup_admin:discounts_availability_exception.delete", kwargs={"pk": object.pk})
                if object.pk else None)
            return get_default_edit_toolbar(self, save_form_id, delete_url=delete_url)

    def get_form_kwargs(self):
        kwargs = super(AvailabilityExceptionEditView, self).get_form_kwargs()
        kwargs["request"] = self.request
        return kwargs


class AvailabilityExceptionDeleteView(DetailView):
    model = AvailabilityException

    def get_queryset(self):
        return AvailabilityException.objects.filter(shops=get_shop(self.request))

    def post(self, request, *args, **kwargs):
        exception = self.get_object()
        exception.delete()
        messages.success(request, _("%s has been deleted.") % exception)
        return HttpResponseRedirect(reverse_lazy("shuup_admin:discounts_availability_exception.list"))
