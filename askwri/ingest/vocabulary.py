"""Controlled vocabularies for document labels: concepts, regions and genres.

Edit these lists to change what the labeler may answer; a reload applies the change.
"""

# WRI's own wri.org tags found in the corpus (2024-2026), spelling kept, case duplicates
# merged, the 11 topics left out. Then terms the corpus covers that WRI's tags lack.
CONCEPTS = (
    *("adaptation", "adaptation finance", "agriculture", "Air Quality", "aquaculture"),
    *("biodiversity", "biofuels", "Buildings", "carbon removal", "circular economy"),
    *("Clean Energy", "climate change", "Climate Equity", "climate finance"),
    *("Climate Governance", "climate policy", "Climate Resilience", "climate science"),
    *("Climate-Friendly Diets", "conservation", "COP29", "COP30", "COP31", "coronavirus"),
    *("corporate sustainability", "data", "deforestation", "development", "electric grid"),
    *("electric mobility", "Energy Access", "environmental justice", "extreme heat"),
    *("fires", "fisheries", "floods", "Food Loss and Waste", "food security"),
    *("Forest and Landscape Restoration", "forest monitoring", "fossil fuels", "Gender"),
    *("GHG emissions", "greenhouse gases", "Green Jobs & Skills", "health"),
    *("Health & Road Safety", "housing", "human rights", "Igniting Innovation"),
    *("Indigenous Peoples & Local Communities", "industry", "infrastructure"),
    *("Integrated Transport", "International Climate Action"),
    *("international climate policy", "land rights", "land use", "landscapes"),
    *("low carbon development", "mapping", "multilateral development banks"),
    *("National Climate Action", "natural infrastructure", "nature-based solutions", "NDC"),
    *("net-zero emissions", "Paris Agreement", "Paying for Paris", "pollution"),
    *("power plants", "public transit", "renewable energy", "restoration", "road safety"),
    *("school bus", "science based targets", "Tracking Climate Action", "transportation"),
    *("U.S. Climate", "U.S. Community Benefits Frameworks", "U.S. Energy", "U.S. policy"),
    *("UNFCCC", "Urban Development", "Urban Efficiency & Climate", "Urban Mobility"),
    *("blue carbon", "blue food", "critical minerals", "illegal fishing", "ocean energy"),
    *("offshore wind", "solar energy"),
)

REGIONS = (
    *("Global", "Africa", "Sub-Saharan Africa", "Middle East and North Africa", "Asia"),
    *("East Asia", "South Asia", "Southeast Asia", "Central Asia", "Europe"),
    *("Latin America and the Caribbean", "North America", "Oceania"),
    "Small island developing states",
)

# What a document is for, as opposed to its form (doc_type: working paper, RFP, ...).
GENRES = (
    *("trend analysis", "progress tracking", "policy analysis", "assessment", "methodology"),
    *("data documentation", "case study", "guide or toolkit", "call for proposals"),
    *("news and updates", "organizational report", "other"),
)
