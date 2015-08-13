# -*- coding: utf-8 -*-
# This file is part of Shoop.
#
# Copyright (c) 2012-2015, Shoop Ltd. All rights reserved.
#
# This source code is licensed under the AGPLv3 license found in the
# LICENSE file in the root directory of this source tree.
import pytest
from shoop.core import settings
from shoop.core.pricing.price import TaxfulPrice, TaxlessPrice
from shoop.testing.factories import get_default_shop, create_product, get_default_customer_group, create_random_person
from shoop.simple_pricing.module import SimplePricingModule
from shoop.simple_pricing.models import SimpleProductPrice


def get_shop_with_tax(include_tax):
    shop = get_default_shop()
    shop.prices_include_tax = include_tax
    shop.save()
    return shop

def initialize_test(rf, include_tax=False):
    shop = get_shop_with_tax(include_tax=include_tax)

    group = get_default_customer_group()
    customer = create_random_person()
    customer.groups.add(group)
    customer.save()

    request = rf.get("/")
    request.shop = shop
    request.customer = customer
    return request, shop, group


@pytest.mark.django_db
def test_shop_specific_cheapest_price_1(rf):
    request, shop, group = initialize_test(rf, False)

    product = create_product("Just-A-Product", shop, default_price=200)

    # determine which is the taxfulness
    price_cls = TaxfulPrice if settings.SHOOP_DEFAULT_PRICES_INCLUDE_TAX else TaxlessPrice

    #SimpleProductPrice.objects.create(product=product, shop=None, price=200)
    SimpleProductPrice.objects.create(product=product, shop=shop, group=group, price=250)
    spm = SimplePricingModule()
    assert product.get_price(spm.get_context_from_request(request), quantity=1) == price_cls(200)  # Cheaper price is valid even if shop-specific price exists


@pytest.mark.django_db
def test_shop_specific_cheapest_price_2(rf):
    request, shop, group = initialize_test(rf, False)

    product = create_product("Just-A-Product-Too", shop, default_price=199)

    price_cls = (TaxfulPrice if shop.prices_include_tax else TaxlessPrice)

    SimpleProductPrice.objects.create(product=product, shop=shop, group=group, price=250)
    spm = SimplePricingModule()
    assert product.get_price(spm.get_context_from_request(request), quantity=1) == price_cls(199)  # Cheaper price is valid even if the other way around applies


@pytest.mark.django_db
def test_set_taxful_price_works(rf):
    request, shop, group = initialize_test(rf, True)

    product = create_product("Anuva-Product", shop, default_price=300)

    # create ssp with higher price
    spp = SimpleProductPrice(product=product, shop=shop, group=group, price=250)
    spp.save()

    spm = SimplePricingModule()
    pricing_context = spm.get_context_from_request(request)
    price_info = product.get_price_info(pricing_context, quantity=1)

    assert price_info.price == TaxfulPrice(250)
    assert price_info.includes_tax

    pp = product.get_price(pricing_context, quantity=1)

    assert pp.includes_tax
    assert pp == TaxfulPrice("250")


@pytest.mark.django_db
def test_set_taxful_price_works_with_product_id(rf):

    request, shop, group = initialize_test(rf, True)

    product = create_product("Anuva-Product", shop, default_price=300)

    # create ssp with higher price
    spp = SimpleProductPrice(product=product, shop=shop, group=group, price=250)
    spp.save()

    spm = SimplePricingModule()
    pricing_context = spm.get_context_from_request(request)
    price_info = spm.get_price_info(pricing_context, product=product.pk, quantity=1)

    assert price_info.price == TaxfulPrice(250)
    assert price_info.includes_tax

    pp = product.get_price(pricing_context, quantity=1)

    assert pp.includes_tax
    assert pp == TaxfulPrice("250")





@pytest.mark.django_db
def test_price_infos(rf):
    request, shop, group = initialize_test(rf, True)

    product_one = create_product("Product_1", shop, default_price=150)
    product_two = create_product("Product_2", shop, default_price=250)

    spp = SimpleProductPrice(product=product_one, shop=shop, group=group, price=100)
    spp.save()

    spp = SimpleProductPrice(product=product_two, shop=shop, group=group, price=200)
    spp.save()

    product_ids = [product_one.pk, product_two.pk]

    spm = SimplePricingModule()
    pricing_context = spm.get_context_from_request(request)
    price_infos = spm.get_price_infos(pricing_context, product_ids)

    assert len(price_infos) == 2
    assert product_one.pk in price_infos
    assert product_two.pk in price_infos

    assert price_infos[product_one.pk].price == TaxfulPrice(100)
    assert price_infos[product_two.pk].price == TaxfulPrice(200)

    assert price_infos[product_one.pk].base_price == TaxfulPrice(100)
    assert price_infos[product_two.pk].base_price == TaxfulPrice(200)


