# Ukiyo-e Relief - renders a DEM as a Japanese woodblock print.
# Copyright (C) 2026  Maksim Boiko <boandch@gmail.com>
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
"""Ukiyo-e Relief: render a DEM as a Japanese woodblock print."""


def classFactory(iface):
    from .plugin import UkiyoeReliefPlugin
    return UkiyoeReliefPlugin(iface)
