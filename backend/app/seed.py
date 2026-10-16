"""Sample catalogue for development. Product copy is placeholder text: replace it with approved content."""
from sqlalchemy import select

from app.models import Product, ProductVariant

SAMPLES = [
    ("cdiab-comfort-step", "C-Diab Comfort Step Slipper", 149900),
    ("cdiab-cushion-plus", "C-Diab Cushion Plus Slipper", 199900),
]


def seed_products(db) -> int:
    added = 0
    for slug, name, price in SAMPLES:
        if db.scalar(select(Product).where(Product.slug == slug)):
            continue
        p = Product(
            slug=slug, name=name, price_paise=price, requires_screening=True,
            description="SAMPLE DATA for development. Replace with approved product copy before launch.",
            intended_use="Indoor foot protection as part of a clinician-guided foot-care routine. Not a treatment for foot ulcers.",
            materials="Placeholder. Confirm materials with the manufacturer.",
            care_instructions="Placeholder. Wipe clean with a damp cloth; air dry.",
            shipping_info="Placeholder. Confirm shipping times and charges.",
            return_info="Placeholder. Confirm the return policy.",
            image_urls=[])
        p.variants = [ProductVariant(size=f"UK {n}", sku=f"{slug}-uk{n}", stock=20) for n in range(6, 11)]
        db.add(p)
        added += 1
    db.commit()
    return added


if __name__ == "__main__":
    from app.core.config import get_settings
    from app.core.db import Base, make_engine, make_session_factory
    s = get_settings()
    engine = make_engine(s.database_url)
    if s.database_url.startswith("sqlite"):
        Base.metadata.create_all(engine)
    with make_session_factory(engine)() as session:
        print(f"Seeded {seed_products(session)} product(s)")
