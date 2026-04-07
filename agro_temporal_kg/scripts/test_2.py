import asyncio
from datetime import datetime

from dotenv import load_dotenv
from graphiti_core.driver.falkordb_driver import FalkorDriver
from pydantic import BaseModel, Field

from agro_temporal_kg.builder import get_graphiti

load_dotenv()


# Custom Entity Types
class Person(BaseModel):
    """A person entity with biographical information."""

    age: int | None = Field(None, description="Age of the person")
    occupation: str | None = Field(None, description="Current occupation")
    location: str | None = Field(None, description="Current location")
    birth_date: datetime | None = Field(None, description="Date of birth")


class Company(BaseModel):
    """A business organization."""

    industry: str | None = Field(None, description="Primary industry")
    founded_year: int | None = Field(None, description="Year company was founded")
    headquarters: str | None = Field(None, description="Location of headquarters")
    employee_count: int | None = Field(None, description="Number of employees")


class Product(BaseModel):
    """A product or service."""

    category: str | None = Field(None, description="Product category")
    price: float | None = Field(None, description="Price in USD")
    release_date: datetime | None = Field(None, description="Product release date")


# Custom Edge Types
class Employment(BaseModel):
    """Employment relationship between a person and company."""

    position: str | None = Field(None, description="Job title or position")
    start_date: datetime | None = Field(None, description="Employment start date")
    end_date: datetime | None = Field(None, description="Employment end date")
    salary: float | None = Field(None, description="Annual salary in USD")
    is_current: bool | None = Field(None, description="Whether employment is current")


class Investment(BaseModel):
    """Investment relationship between entities."""

    amount: float | None = Field(None, description="Investment amount in USD")
    investment_type: str | None = Field(None, description="Type of investment (equity, debt, etc.)")
    stake_percentage: float | None = Field(None, description="Percentage ownership")
    investment_date: datetime | None = Field(None, description="Date of investment")


class Partnership(BaseModel):
    """Partnership relationship between companies."""

    partnership_type: str | None = Field(None, description="Type of partnership")
    duration: str | None = Field(None, description="Expected duration")
    deal_value: float | None = Field(None, description="Financial value of partnership")


entity_types = {"Person": Person, "Company": Company, "Product": Product}

edge_types = {
    "Employment": Employment,
    "Investment": Investment,
    "Partnership": Partnership,
}

edge_type_map = {
    ("Person", "Company"): ["Employment"],
    ("Company", "Company"): ["Partnership", "Investment"],
    ("Person", "Person"): ["Partnership"],
    ("Entity", "Entity"): ["Investment"],  # Apply to any entity type
}


async def main():
    graphiti = get_graphiti("test-graph")
    driver: FalkorDriver = graphiti.driver
    await driver._get_graph(None).delete()

    await graphiti.add_episode(
        name="Business Update",
        episode_body="Sarah joined TechCorp as CTO in January 2023 with a $200K salary. TechCorp partnered with DataCorp in a $5M deal.",
        source_description="Business news",
        reference_time=datetime.now(),
        entity_types=entity_types,
        edge_types=edge_types,
        edge_type_map=edge_type_map,
    )


if __name__ == "__main__":
    # Run the async main function
    asyncio.run(main())
