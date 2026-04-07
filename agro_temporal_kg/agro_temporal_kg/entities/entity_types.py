from typing import Optional

from pydantic import BaseModel, Field

# -------------------------
# Entity / Node Types
# -------------------------


class Plant(BaseModel):
    """A plant species, variety, or cultivar used in agriculture or gardening."""

    species: Optional[str] = Field(None, description="Scientific or common species name")
    variety: Optional[str] = Field(None, description="Specific variety or cultivar name")


class PlantPart(BaseModel):
    """A specific part of a plant (e.g., root, stem, leaf, fruit, seed)."""

    part_name: Optional[str] = Field(
        None, description="Name of the plant part, e.g. 'root', 'leaf', 'fruit', 'seed'"
    )
    function: Optional[str] = Field(None, description="Function or purpose of this plant part")


class Pest(BaseModel):
    """A pest organism that threatens agricultural plants or crops."""

    pest_type: Optional[str] = Field(
        None, description="Type of pest, e.g. 'insect', 'fungus', 'bacteria', 'virus', 'weed'"
    )
    common_name: Optional[str] = Field(None, description="Common name of the pest")


class Practice(BaseModel):
    """An agricultural or gardening practice, technique, or management activity."""

    practice_type: Optional[str] = Field(
        None,
        description="Type of practice, e.g. 'sowing', 'planting', 'pruning', 'harvesting', 'fertilizing'",
    )
    description: Optional[str] = Field(None, description="Description of the practice")


class SoilType(BaseModel):
    """A type of soil or soil condition relevant to agriculture."""

    texture: Optional[str] = Field(
        None, description="Soil texture, e.g. 'clay', 'sandy', 'loamy', 'silt'"
    )
    ph_range: Optional[str] = Field(
        None, description="pH range or preference, e.g. 'acidic', 'neutral', 'alkaline'"
    )


class Condition(BaseModel):
    """An environmental condition, state, or circumstance affecting agriculture."""

    condition_type: Optional[str] = Field(
        None,
        description="Type of condition, e.g. 'weather', 'disease', 'nutrient_deficiency', 'moisture'",
    )
    severity: Optional[str] = Field(
        None, description="Severity level, e.g. 'mild', 'moderate', 'severe'"
    )


class Structure(BaseModel):
    """A physical structure or infrastructure used in agriculture or gardening."""

    structure_type: Optional[str] = Field(
        None,
        description="Type of structure, e.g. 'greenhouse', 'cold_frame', 'bed', 'pot', 'trellis'",
    )
    purpose: Optional[str] = Field(None, description="Purpose or function of the structure")


class Time(BaseModel):
    """A temporal reference point, period, or timing information in agriculture."""

    time_type: Optional[str] = Field(
        None,
        description="Type of time reference, e.g. 'season', 'month', 'week', 'day', 'growing_stage'",
    )
    season: Optional[str] = Field(
        None, description="Season name, e.g. 'spring', 'summer', 'fall', 'winter'"
    )


class Location(BaseModel):
    """A geographic location, field, farm, or region relevant to agriculture."""

    location_type: Optional[str] = Field(
        None, description="Type of location, e.g. 'field', 'farm', 'region', 'zone', 'garden'"
    )
    location_name: Optional[str] = Field(None, description="Name of the location")


class Input(BaseModel):
    """An agricultural input, material, or resource used in farming practices."""

    input_type: Optional[str] = Field(
        None,
        description="Type of input, e.g. 'fertilizer', 'seed', 'pesticide', 'compost', 'mulch', 'amendment'",
    )
    input_name: Optional[str] = Field(None, description="Name or brand of the input")


class Equipment(BaseModel):
    """A tool, machine, or piece of equipment used in agriculture."""

    equipment_type: Optional[str] = Field(
        None,
        description="Type of equipment, e.g. 'tractor', 'irrigation_system', 'pruning_shears', 'hoe', 'harvester'",
    )
    equipment_name: Optional[str] = Field(None, description="Name or model of the equipment")


class Disease(BaseModel):
    """A plant disease or pathological condition affecting crops."""

    disease_type: Optional[str] = Field(
        None,
        description="Type of disease, e.g. 'fungal', 'bacterial', 'viral', 'physiological_disorder'",
    )
    common_name: Optional[str] = Field(None, description="Common name of the disease")


class Weather(BaseModel):
    """A weather event, condition, or climate pattern affecting agriculture."""

    weather_type: Optional[str] = Field(
        None,
        description="Type of weather, e.g. 'rain', 'frost', 'drought', 'storm', 'heat_wave', 'wind'",
    )
    severity: Optional[str] = Field(
        None, description="Severity or intensity, e.g. 'light', 'moderate', 'heavy', 'extreme'"
    )


class Nutrient(BaseModel):
    """A nutrient, mineral, or chemical element important for plant growth."""

    nutrient_type: Optional[str] = Field(
        None,
        description="Type of nutrient, e.g. 'macronutrient', 'micronutrient', 'nitrogen', 'phosphorus', 'potassium'",
    )
    nutrient_name: Optional[str] = Field(None, description="Name of the nutrient or element")


class Organism(BaseModel):
    """A beneficial organism or biological agent used in agriculture."""

    organism_type: Optional[str] = Field(
        None,
        description="Type of organism, e.g. 'beneficial_insect', 'pollinator', 'microbe', 'earthworm', 'predator'",
    )
    common_name: Optional[str] = Field(None, description="Common name of the organism")



#Added 
class Animal(BaseModel):
    """An animal species relevant to agriculture or farming."""

    animal_type: Optional[str] = Field(
        None,
        description="Type of animal, e.g. 'horse', 'chicken', 'cow', 'sheep', 'goat'",
    )
    common_name: Optional[str] = Field(None, description="Common name of the animal")

class People(BaseModel):
    """A person or group involved in agricultural activities."""

    role: Optional[str] = Field(
        None,
        description="Role of the person, e.g. 'farmer', 'worker', 'manager', 'technician'",
    )
    # 'name' is a reserved/protected attribute in the graph schema for some node types.
    # Use 'person_name' to avoid conflicts with reserved attribute names while still
    # capturing the person's name. This avoids errors like:
    # "name cannot be used as an attribute for People as it is a protected attribute name." 
    person_name: Optional[str] = Field(None, description="Name of the person or group")

class Institution(BaseModel):
    """An institution or organization related to agriculture or contributed to agriculture."""

    institution_type: Optional[str] = Field(
        None,
        description="Type of institution, e.g. 'research_institute', 'university', 'government_agency'",
    )
    institution_name: Optional[str] = Field(None, description="Name of the institution")

# -------------------------
# Entity Types Mapping
# -------------------------


entity_types = {
    "Plant": Plant,
    "PlantPart": PlantPart,
    "Pest": Pest,
    "Practice": Practice,
    "SoilType": SoilType,
    "Condition": Condition,
    "Structure": Structure,
    "Time": Time,
    "Location": Location,
    "Input": Input,
    "Equipment": Equipment,
    "Disease": Disease,
    "Weather": Weather,
    "Nutrient": Nutrient,
    "Organism": Organism,
    "Animal": Animal, #Added
    "People": People, #Added
    "Institution": Institution, #Added
}
