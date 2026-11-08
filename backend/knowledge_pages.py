"""The pages of the WHO the corpus is built from.

Kept apart from the rest, with no import: the script that fetches them must
run without a database, a secret or anything else.
"""

# (the slug of the page, the title of the document)
PAGES = [
    ("emergency-contraception", "Contraception d'urgence"),
    ("family-planning-contraception", "Planification familiale et méthodes de contraception"),
    ("abortion", "Avortement"),
    ("hiv-aids", "VIH/sida"),
    ("violence-against-women", "Violence faite aux femmes"),
    ("abuse-of-older-people", "Violences faites aux personnes âgées"),
    ("adolescent-pregnancy", "Grossesse chez l'adolescente"),
    ("chlamydia", "Chlamydia"),
    ("syphilis", "Syphilis"),
    ("menopause", "Ménopause"),
]
