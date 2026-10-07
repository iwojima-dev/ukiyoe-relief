"""Ukiyo-e Relief: render a DEM as a Japanese woodblock print."""


def classFactory(iface):
    from .plugin import UkiyoeReliefPlugin
    return UkiyoeReliefPlugin(iface)
