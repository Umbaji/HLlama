import unittest

from helpers.health import select_closest_place

USER = (6.1964898, 1.2011572)


def place(name, km_north, types=("doctor", "health"), status="OPERATIONAL", place_id=None):
    """A Google Places result `km_north` kilometres north of USER."""
    return {
        "place_id": place_id or name,
        "name": name,
        "types": list(types),
        "business_status": status,
        "geometry": {"location": {"lat": USER[0] + km_north / 111.2, "lng": USER[1]}},
    }


def pick(category, candidates, radius_km=10):
    selected = select_closest_place(category, candidates, USER, radius_km)
    return selected[0]["name"] if selected else None


class NearestPlaceSelectionTests(unittest.TestCase):
    # The two cases below reproduce, in Google's own order, what the production
    # API returned for "doctor" at the coordinates users actually sent.

    def test_clinic_skips_the_mislabelled_firm_google_ranks_first(self) -> None:
        candidates = [
            place("Cabinet d'Investigation Economique", 0.32),
            place("Clinique Rocher", 0.40),
            place("Phaved Cabinet Veterinaire", 0.60),
            place("Nouveau Bâtiment Ministère de la Santé et de l'Hygiène", 0.70),
        ]
        self.assertEqual(pick("clinic", candidates), "Clinique Rocher")

    def test_clinic_skips_the_optician_and_finds_the_gynaecologist(self) -> None:
        candidates = [
            place("CENTRE DE BASSE VISION ET OPTIQUE GENERALE", 1.28),
            place("CABINET SPECIALISE DE GYNECOLOGIE ELLE", 1.35),
            place("TATOUNOU (Tout sur l'oeil)", 1.40),
        ]
        self.assertEqual(pick("clinic", candidates), "CABINET SPECIALISE DE GYNECOLOGIE ELLE")

    def test_pharmacy_skips_a_veterinary_supplier_typed_as_pharmacy(self) -> None:
        candidates = [
            place("Véto négoces", 0.20, types=("pharmacy", "veterinary_care", "store")),
            place("Pharmacie Vigueur", 0.44, types=("pharmacy", "store", "health")),
        ]
        self.assertEqual(pick("pharmacy", candidates), "Pharmacie Vigueur")

    def test_a_matching_name_beats_a_closer_generic_match(self) -> None:
        candidates = [
            place("cabinet cardiologique myosotis", 0.30),
            place("Clinique Médico Cardiologique Coeur de Grace", 0.90),
        ]
        self.assertEqual(
            pick("clinic", candidates), "Clinique Médico Cardiologique Coeur de Grace"
        )

    def test_distance_decides_between_equally_good_matches(self) -> None:
        candidates = [
            place("Clinique Loin", 2.0),
            place("CMS Démakpoé", 0.8),
        ]
        self.assertEqual(pick("clinic", candidates), "CMS Démakpoé")

    def test_a_generic_match_is_still_returned_when_nothing_better_exists(self) -> None:
        self.assertEqual(
            pick("clinic", [place("cabinet cardiologique myosotis", 0.30)]),
            "cabinet cardiologique myosotis",
        )

    def test_accented_names_are_recognised(self) -> None:
        candidates = [
            place("Chez Prof Rhumatologue", 0.2, types=("hospital", "health")),
            place("Hôpital de Bè", 0.9, types=("hospital", "health")),
        ]
        self.assertEqual(pick("hospital", candidates), "Hôpital de Bè")

    def test_english_clinic_names_are_recognised(self) -> None:
        candidates = [
            place("Chez Prof Rhumatologue", 0.2, types=("hospital", "health")),
            place("Clinical Kômombo", 0.5, types=("hospital", "health")),
            place("CMS Démakpoé", 0.53, types=("hospital", "health")),
        ]
        self.assertEqual(pick("hospital", candidates), "Clinical Kômombo")

    def test_places_outside_the_radius_are_not_recommended(self) -> None:
        self.assertIsNone(pick("pharmacy", [place("Pharmacie Lointaine", 12.0)], radius_km=10))

    def test_closed_places_are_skipped(self) -> None:
        candidates = [
            place("Pharmacie Fermée", 0.1, status="CLOSED_PERMANENTLY"),
            place("Pharmacie Ouverte", 0.5),
        ]
        self.assertEqual(pick("pharmacy", candidates), "Pharmacie Ouverte")

    def test_a_place_returned_by_both_type_queries_is_considered_once(self) -> None:
        duplicate = place("Clinique Rocher", 0.4, place_id="abc")
        self.assertEqual(pick("clinic", [duplicate, dict(duplicate)]), "Clinique Rocher")

    def test_no_acceptable_candidate_returns_none(self) -> None:
        self.assertIsNone(pick("clinic", [place("Cabinet d'Investigation Economique", 0.3)]))


if __name__ == "__main__":
    unittest.main()
