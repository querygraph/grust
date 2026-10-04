"""Apache SedonaDB functions exported through the DataFusion 55.1 capsule API."""


class SedonaExtension:
    def manifest(self):
        # Keep validation possible before importing any native capsule provider.
        return {
            "name": "sedona",
            "version": "0.1.0",
            "api_version": 1,
            "datafusion_version": "55.1.0",
            "arrow_version": "59.3.0",
            "placement": "any",
            "relation_types": [],
        }

    def bind(self, session_id):
        from ._native import BoundSedona

        return BoundSedona(session_id)


extension = SedonaExtension()
