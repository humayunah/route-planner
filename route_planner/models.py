from __future__ import annotations

import typing

from django.db import models

from .managers import FuelStationManager


class FuelStation(models.Model):
    opis_id = models.IntegerField(unique=True)
    name = models.CharField(max_length=255)
    address = models.CharField(max_length=500)
    city = models.CharField(max_length=100)
    state = models.CharField(max_length=10)
    rack_id = models.IntegerField()
    retail_price = models.FloatField()
    latitude = models.FloatField(null=True, blank=True, db_index=True)
    longitude = models.FloatField(null=True, blank=True, db_index=True)

    objects = FuelStationManager()

    class Meta:
        indexes: typing.ClassVar = [models.Index(fields=["state", "city"])]

    def __str__(self) -> str:
        return f"{self.name} ({self.city}, {self.state}) - ${self.retail_price:.3f}"
