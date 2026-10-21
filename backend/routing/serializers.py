from datetime import timedelta

from django.utils import timezone
from rest_framework import serializers

MAX_DAYS_AHEAD = 7


class PointSerializer(serializers.Serializer):
    lat = serializers.FloatField(min_value=-90, max_value=90)
    lon = serializers.FloatField(min_value=-180, max_value=180)


class PlanRequestSerializer(serializers.Serializer):
    origin = PointSerializer()
    destination = PointSerializer()
    departure = serializers.DateTimeField()
    load_lb = serializers.FloatField(min_value=0, max_value=120_000)
    interval_mi = serializers.ChoiceField(choices=[10, 25, 50], default=25)

    def validate_departure(self, value):
        now = timezone.now()
        if value < now - timedelta(hours=1):
            raise serializers.ValidationError("Departure can't be in the past.")
        if value > now + timedelta(days=MAX_DAYS_AHEAD):
            raise serializers.ValidationError(f"Forecasts are only reliable up to {MAX_DAYS_AHEAD} days ahead.")
        return value

    def validate(self, attrs):
        o, d = attrs["origin"], attrs["destination"]
        if abs(o["lat"] - d["lat"]) < 1e-3 and abs(o["lon"] - d["lon"]) < 1e-3:
            raise serializers.ValidationError("Origin and destination are the same place.")
        return attrs


class HeatmapRequestSerializer(serializers.Serializer):
    routes = serializers.ListField(
        child=serializers.ListField(child=serializers.ListField(child=serializers.FloatField(), min_length=2, max_length=2), min_length=2),
        min_length=1,
        max_length=3,
    )
    start = serializers.DateTimeField()
    load_lb = serializers.FloatField(min_value=0, max_value=120_000)
