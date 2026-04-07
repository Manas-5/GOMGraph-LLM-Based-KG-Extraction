#v2
from pydantic import BaseModel


# --- Causal / Impact ---

class AffectedBy(BaseModel):
    """Entity affected by a factor (pest, disease, weather, condition)."""


class Causes(BaseModel):
    """Entity causes an effect/outcome/condition."""


class ResistantTo(BaseModel):
    """Entity resistant to a stressor."""


# --- Dependency ---

class Requires(BaseModel):
    """Requirement relationship: entity requires an input, nutrient, condition, or equipment."""


class Uses(BaseModel):
    """Usage relationship: practice or entity uses an input, equipment, or resource."""


# --- Spatial ---

class LocatedInOrAt(BaseModel):
    """Entity located in or at a place (generalized spatial relation)."""


class OriginatesFrom(BaseModel):
    """Entity originates from a source."""


# --- Composition ---

class ContainsOrHasPart(BaseModel):
    """Entity contains or has a part/component/sub-entity."""


class PartOf(BaseModel):
    """Entity is part of a larger whole (part-of relation)."""


class VarietyOf(BaseModel):
    """Entity is a variety of another entity (taxonomy/variety relation)."""


# --- Treatment ---

class TreatedWithSomething(BaseModel):
    """Treatment relation variant: treated with some agent/input/practice."""


class ProtectionRelation(BaseModel):
    """Protective association between entities."""


# --- Agricultural ---

class PlantedIn(BaseModel):
    """Planting location/container: entity planted in something."""


class GrowthStageRelatedTo(BaseModel):
    """Links an entity to something related to a growth stage."""


class SeedingRelationship(BaseModel):
    """Seeding details for an entity."""


class PropagationMethod(BaseModel):
    """Propagation method used for an entity."""


# --- Temporal ---

class Precedes(BaseModel):
    """Temporal sequence relationship: one event or practice precedes another."""


class Follows(BaseModel):
    """Temporal/sequence relation: one event/practice follows another."""


class TemporalAssociation(BaseModel):
    """General temporal association between entities/events."""


class SeasonalRelatedness(BaseModel):
    """General seasonal relatedness association."""


# --- Properties ---

class HasCharacteristic(BaseModel):
    """Entity has a characteristic."""


class HasMonetaryValue(BaseModel):
    """Entity has monetary value."""


# --- Comparison ---

class ComparesTo(BaseModel):
    """One entity compared to another."""


class AlternativeOrReplacement(BaseModel):
    """One entity can substitute for or replace another."""


class DiffersFrom(BaseModel):
    """Entity differs from another entity (general differs-from relation)."""


# --- General ---

class AssociatedWith(BaseModel):
    """General association between entities."""


class ProductionRelation(BaseModel):
    """Production relationship (general production link)."""

class GrownIn(BaseModel):
    """Location relationship: where a plant is grown."""


edge_types = {
    "AffectedBy": AffectedBy,
    "Causes": Causes,
    "ResistantTo": ResistantTo,
    "Requires": Requires,
    "Uses": Uses,
    "LocatedInOrAt": LocatedInOrAt,
    "OriginatesFrom": OriginatesFrom,
    "ContainsOrHasPart": ContainsOrHasPart,
    "PartOf": PartOf,
    "VarietyOf": VarietyOf,
    "TreatedWithSomething": TreatedWithSomething,
    "ProtectionRelation": ProtectionRelation,
    "PlantedIn": PlantedIn,
    "GrowthStageRelatedTo": GrowthStageRelatedTo,
    "SeedingRelationship": SeedingRelationship,
    "PropagationMethod": PropagationMethod,
    "Precedes": Precedes,
    "Follows": Follows,
    "TemporalAssociation": TemporalAssociation,
    "SeasonalRelatedness": SeasonalRelatedness,
    "HasCharacteristic": HasCharacteristic,
    "HasMonetaryValue": HasMonetaryValue,
    "ComparesTo": ComparesTo,
    "AlternativeOrReplacement": AlternativeOrReplacement,
    "DiffersFrom": DiffersFrom,
    "AssociatedWith": AssociatedWith,
    "ProductionRelation": ProductionRelation,
    "GrownIn": GrownIn,
}

#v1
# from pydantic import BaseModel


# class PlantedAt(BaseModel):
#     """Planting relationship: when and where a plant was planted."""


# class HarvestedAt(BaseModel):
#     """Harvest relationship: when a plant or crop was harvested."""


# class GrownIn(BaseModel):
#     """Location relationship: where a plant is grown or a practice is performed."""


# class TreatedWith(BaseModel):
#     """Treatment relationship: entity treated with an input, practice, or equipment."""


# class Requires(BaseModel):
#     """Requirement relationship: entity requires an input, nutrient, condition, or equipment."""


# class Uses(BaseModel):
#     """Usage relationship: practice or entity uses an input, equipment, or resource."""


# class Prefers(BaseModel):
#     """Preference relationship: entity prefers a soil type, condition, or environment."""


# class OccursAt(BaseModel):
#     """Temporal relationship: when a practice, event, or condition occurs."""


# class Precedes(BaseModel):
#     """Temporal sequence relationship: one event or practice precedes another."""


# class Produces(BaseModel):
#     """Production relationship: entity produces a plant part, yield, or output."""


# class LocatedIn(BaseModel):
#     """Spatial relationship: entity located in a geographic area or structure."""


# class CauseOf(BaseModel):
#     """Causal relationship: entity causes an effect, outcome, or condition."""


# class AccessibilityDifference(BaseModel):
#     """Difference in accessibility between entities or contexts."""


# class AffectedBy(BaseModel):
#     """Entity affected by a factor (pest, disease, weather, condition)."""


# class AgriculturalTechnique(BaseModel):
#     """Links an entity to an agricultural technique."""


# class AlsoKnownByName(BaseModel):
#     """Entity also known by another name (alias)."""


# class AlternativeOrReplacement(BaseModel):
#     """One entity can substitute for or replace another."""


# class AppealRenewal(BaseModel):
#     """Appeal or renewal event relating to an entity/decision."""


# class AsparagusColorVariety(BaseModel):
#     """Asparagus variety characterized by color."""


# class AssignedTo(BaseModel):
#     """Entity assigned to a person/team/organization/category."""


# class AssociatedWith(BaseModel):
#     """General association between entities."""


# class AttachedWith(BaseModel):
#     """Something attached with/to another entity."""


# class AttendeeOfEvent(BaseModel):
#     """Entity/person attends an event."""


# class AvailableAtLocation(BaseModel):
#     """Entity available at a given location."""


# class AwardedForFounding(BaseModel):
#     """Award/recognition granted for founding an entity/organization."""


# class BearsFoodIn(BaseModel):
#     """Plant bears food (fruit/seed/pod) during a period."""


# class BellTimingInfo(BaseModel):
#     """Timing information for a bell/notification."""


# class BlanchingPurpose(BaseModel):
#     """Purpose of blanching for a crop/part."""


# class BlanchingSource(BaseModel):
#     """Material/source used to blanch (e.g. soil, cover, mulch)."""


# class BuriedInGround(BaseModel):
#     """Entity is buried in the ground (storage/overwintering/anchoring)."""


# class CabbageHarvestingTime(BaseModel):
#     """When cabbage is typically harvested."""


# class CarrotContainerRelation(BaseModel):
#     """Carrots stored/kept in a container or method."""


# class CategoryRelationship(BaseModel):
#     """Entity belongs to or relates to a category."""


# class Causes(BaseModel):
#     """Entity causes an effect/outcome/condition."""


# class ComparesTo(BaseModel):
#     """One entity compared to another."""


# class CompareTo(BaseModel):
#     """Comparison edge variant."""


# class CompetitionStatus(BaseModel):
#     """Competitive status of an entity in a context."""


# class CompetitivePressureFromExternalFactors(BaseModel):
#     """Competitive pressure caused by external factors."""


# class ConditionallyTriggered(BaseModel):
#     """Relation/event triggered under specific conditions."""


# class ConditionsForSuccessfulOverwintering(BaseModel):
#     """Conditions required for successful overwintering."""


# class ConstructingWindbreaks(BaseModel):
#     """Windbreak construction guidance/association."""


# class ConsumerOf(BaseModel):
#     """Entity consumes another entity/resource."""


# class Containment(BaseModel):
#     """Entity contained within another."""


# class ContainmentIssue(BaseModel):
#     """Issue or failure related to containment."""


# class ContainmentLocation(BaseModel):
#     """Where containment is implemented or relevant."""


# class Contains(BaseModel):
#     """Entity contains components/nutrients/parts."""

# # check for simplfication
# class ContainsMannequins(BaseModel):
#     """Entity contains mannequins (domain-specific)."""


# class ContainsPaths(BaseModel):
#     """Entity contains paths (layout/structure)."""


# class CreationTime(BaseModel):
#     """Creation time of an entity/artifact/event."""


# class CropCharacteristic(BaseModel):
#     """A crop has a characteristic."""


# class CultivatedTaxonomyRelationship(BaseModel):
#     """Cultivated taxonomy linkage (cultivar/variety/species/group)."""


# class DeficiencyRelationship(BaseModel):
#     """Entity related to a nutrient deficiency state or effect."""


# class DependentOn(BaseModel):
#     """Entity depends on another entity/condition."""


# class DiffersFromEntity(BaseModel):
#     """Entity differs from another entity."""


# class DuplicateTranslation(BaseModel):
#     """Duplicate translation/labeling artifact."""


# class EarlierThan(BaseModel):
#     """One event/date is earlier than another."""


# class EarlyHarvest(BaseModel):
#     """Early harvest relative to normal."""


# class EdgeAssociation(BaseModel):
#     """Meta association between relations (mapping/alignment)."""


# class ElevatedBy(BaseModel):
#     """An attribute is increased/elevated by a factor."""


# class Endogamy(BaseModel):
#     """Endogamy relation within a group."""


# class EquipmentRelationship(BaseModel):
#     """Links an entity/practice to equipment used."""


# class ExemptFromSubstitution(BaseModel):
#     """Entity is exempt from substitution rules."""


# class ExemptFromTransplanting(BaseModel):
#     """Entity is exempt from transplanting requirements."""


# class FamilyRelationship(BaseModel):
#     """Entity belongs to a family (taxonomic or social)."""


# class FarmEquipmentRelationship(BaseModel):
#     """Links farm equipment to an activity or entity."""


# class FearResponse(BaseModel):
#     """Response triggered by a fear-inducing stimulus."""


# class FinancialExchange(BaseModel):
#     """Financial transaction between entities."""


# class FoundingDate(BaseModel):
#     """Founding date of an entity."""


# class FrameAssociation(BaseModel):
#     """Association within a semantic frame."""


# class GerminationContext(BaseModel):
#     """Context influencing germination."""


# class GrowBelowGround(BaseModel):
#     """Entity grows below ground."""


# class GrowthStageRelation(BaseModel):
#     """Links an entity to a growth stage."""


# class HairConduceiveToGrowth(BaseModel):
#     """Structures conducive to growth (domain-specific)."""


# class HasAssociatedEntity(BaseModel):
#     """Entity has an associated entity."""


# class HasCharacteristic(BaseModel):
#     """Entity has a characteristic."""


# class HasDimensionalAttribute(BaseModel):
#     """Entity has a dimensional attribute."""


# class HasDimensionalReach(BaseModel):
#     """Extent/reach of an entity."""


# class HasHighMaintenanceRequirement(BaseModel):
#     """Entity requires high maintenance."""


# class HasMonetaryValue(BaseModel):
#     """Entity has monetary value."""


# class HasStructuralElements(BaseModel):
#     """Entity has structural elements."""


# class HeatTransferRelationship(BaseModel):
#     """Heat transfer relation between entities."""


# class HighQuality(BaseModel):
#     """Entity characterized as high quality."""


# class Hypernymy(BaseModel):
#     """Broader-term (is-a) relationship."""


# class ImpactOnDevelopment(BaseModel):
#     """Impact on development stage or progress."""


# class InhibitsDevelopment(BaseModel):
#     """Factor inhibits development of an entity."""


# class InstanceOf(BaseModel):
#     """Entity is an instance of a class."""


# class IrrigationRelation(BaseModel):
#     """Irrigation applied to an entity."""


# class IsRelevantTo(BaseModel):
#     """Entity relevant to a domain/context."""


# class LayeringRelationship(BaseModel):
#     """Layering propagation technique applied."""


# class LeadPipeMaterialOrAlternative(BaseModel):
#     """Lead pipe material or safer alternative."""


# class LeftInPlace(BaseModel):
#     """Entity left in place intentionally."""


# class LettuceTypeAssociation(BaseModel):
#     """Association to a lettuce type."""


# class LimitationRelationship(BaseModel):
#     """Limitation/constraint affecting an entity."""


# class LocationRelationship(BaseModel):
#     """General location association."""


# class ManagedByOrganizationOrTeam(BaseModel):
#     """Entity managed by an organization or team."""


# class ManureRelated(BaseModel):
#     """Relationship related to manure use/management."""


# class MarketingRelationship(BaseModel):
#     """Marketing association for an entity."""


# class MarketGardenerCharacteristics(BaseModel):
#     """Characteristics/profile of a market gardener."""


# class MarketGardeningRelated(BaseModel):
#     """Related to market gardening domain."""


# class MaturityDateRelation(BaseModel):
#     """Maturity date association."""


# class MeasurementRelation(BaseModel):
#     """Measurement related to an entity."""


# class MembershipRelationship(BaseModel):
#     """Entity is a member of an organization/group."""


# class MilledToFinish(BaseModel):
#     """Entity milled/processed to a finish."""


# class MonthlyComparisonOfSuccess(BaseModel):
#     """Monthly comparison of success/performance."""


# class MonthlyOccurrence(BaseModel):
#     """Event occurs monthly."""


# class MovedTo(BaseModel):
#     """Entity moved to a new location."""


# class MulchRelation(BaseModel):
#     """Mulch applied or related."""


# class NotGrown(BaseModel):
#     """Crop not grown in a context."""


# class NotRelatedTo(BaseModel):
#     """Entities explicitly not related."""


# class OptionalRelationship(BaseModel):
#     """Optional (non-mandatory) relationship."""


# class OriginatesFrom(BaseModel):
#     """Entity originates from a source."""


# class OverlapsWith(BaseModel):
#     """Entities overlap spatially or conceptually."""


# class PartOfRelationship(BaseModel):
#     """Entity is part of a larger whole."""


# class PeopleRelationshipEconomicActivity(BaseModel):
#     """Economic activity involving people."""


# class PilesInWetlands(BaseModel):
#     """Piles located in wetlands (environmental context)."""


# class PlantableStatus(BaseModel):
#     """Plantable status of an entity."""


# class PlantingRelationship(BaseModel):
#     """Planting association for an entity."""


# class PoliceActionAffects(BaseModel):
#     """Police/administrative action affecting an entity."""


# class PracticeOf(BaseModel):
#     """Entity practices something."""


# class PreferredCondition(BaseModel):
#     """Preferred environmental condition."""


# class PreparationStatus(BaseModel):
#     """Preparation status of an entity."""


# class ProducesGuideFor(BaseModel):
#     """Produces a guide for a target entity/audience."""


# class ProducesOutput(BaseModel):
#     """Produces a specific output."""


# class ProneToDegradation(BaseModel):
#     """Entity prone to degradation."""


# class PropagationMethod(BaseModel):
#     """Propagation method used for an entity."""


# class PropagationSource(BaseModel):
#     """Source material for propagation."""


# class ProtectedOrCoveredWithMaterials(BaseModel):
#     """Entity protected or covered with materials."""


# class ProtectionRelation(BaseModel):
#     """Protective association between entities."""


# class ProtectsFrom(BaseModel):
#     """Entity protects from a threat."""


# class PruneRelation(BaseModel):
#     """Pruning association for an entity."""


# class RadishOrigin(BaseModel):
#     """Origin information for radish."""


# class RateOfChange(BaseModel):
#     """Rate of change over time."""


# class ReceiverOf(BaseModel):
#     """Entity receives something from another."""


# class RegionSpecific(BaseModel):
#     """Applies specifically to a region."""


# class RelatedToFinancialInformation(BaseModel):
#     """Related to financial information."""


# class RelatedToGardenLocations(BaseModel):
#     """Related to garden locations."""


# class RelatedToGreens(BaseModel):
#     """Related to leafy greens."""


# class RemovableInSunlight(BaseModel):
#     """Removable or dissipates in sunlight."""


# class RemovalRelation(BaseModel):
#     """Removal of something from something else."""


# class RemovedFrom(BaseModel):
#     """Entity removed from a location/source."""


# class RentalLocation(BaseModel):
#     """Entity rented at/for a location."""


# class RepositionsObjects(BaseModel):
#     """Entity repositions objects."""


# class Requirement(BaseModel):
#     """General requirement constraint."""


# class ResistantTo(BaseModel):
#     """Entity resistant to a stressor."""


# class RetainsViabilityFor(BaseModel):
#     """Retains viability for a duration."""


# class SeasonalAssociation(BaseModel):
#     """Associated with a season."""


# class SeasonalPattern(BaseModel):
#     """Recurring seasonal pattern."""


# class SeedingRelatedDestruction(BaseModel):
#     """Destruction related to seeding stage."""


# class SeedingRelationship(BaseModel):
#     """Seeding details for an entity."""


# class SelectedOrPicked(BaseModel):
#     """Entity selected or picked."""


# class SequenceRelationship(BaseModel):
#     """Sequence/order between entities/events."""


# class SimilarityRelationship(BaseModel):
#     """Entities similar by some basis."""


# class SoilRelationship(BaseModel):
#     """Entity related to soil type/properties."""


# class SourceOfOrigins(BaseModel):
#     """Source of origin information."""


# class SouthOriented(BaseModel):
#     """Entity oriented toward the south."""


# class SpatialRelationship(BaseModel):
#     """Spatial relation between entities."""


# class SproutsFromLocation(BaseModel):
#     """Entity sprouts from a location/substrate."""


# class StartedInvestigation(BaseModel):
#     """Investigation started for an entity."""


# class ThinningTechnique(BaseModel):
#     """Thinning technique used."""


# class TimeRelationship(BaseModel):
#     """Generic time association."""


# class TransplantationEvent(BaseModel):
#     """Transplantation event details."""


# class TransportationMethod(BaseModel):
#     """Transportation method used."""


# class TreatedBy(BaseModel):
#     """Entity treated by an agent/practice."""


# class UsedWithPeas(BaseModel):
#     """Used with peas (companion/rotation/recipe/practice)."""


# class UtilizedInContextOf(BaseModel):
#     """Entity utilized in a specific context."""


# class VariationOf(BaseModel):
#     """Entity is a variation of another."""


# class VisualRepresentation(BaseModel):
#     """Visual representation of an entity."""


# class WeatherSensitivity(BaseModel):
#     """Sensitivity to weather conditions."""

# from pydantic import BaseModel


# class AffectedByAuthorityAction(BaseModel):
#     """Entity is affected by an authority/administrative/police action."""


# class AimedAtProducingResourceFor(BaseModel):
#     """Action/practice aimed at producing a resource for a target entity/group."""


# class AlsoKnownAs(BaseModel):
#     """Entity also known as another name/title (alias/synonym)."""


# class AssociatedWithOrganizationOrPersonnel(BaseModel):
#     """Entity associated with an organization, team, or personnel."""


# class AttendeeOfReligiousEvent(BaseModel):
#     """Entity/person attends a religious event."""


# class AvailableInLocation(BaseModel):
#     """Entity is available in a given location/region."""


# class AwardedPrize(BaseModel):
#     """Entity/person awarded a prize/award."""


# class BasedOn(BaseModel):
#     """Entity based on another entity/source/idea."""


# class BeforeRipeningOnVine(BaseModel):
#     """Temporal/condition note: occurs before ripening on the vine."""


# class BellRelatedInfo(BaseModel):
#     """General information related to a bell/notification."""


# class BlanchingBoundary(BaseModel):
#     """Boundary/limit/extent of blanching (where/how far blanching applies)."""


# class CabbageHarvestingAge(BaseModel):
#     """Typical cabbage harvesting age (age at harvest)."""


# class CarrotIsLocatedInOrOn(BaseModel):
#     """Carrot located in/on a place or substrate (spatial placement)."""


# class CategoryOf(BaseModel):
#     """Entity is a category/type of another (category-of relation)."""


# class CollarPosition(BaseModel):
#     """Position/location of a collar feature relative to an entity."""


# class CompareAttribute(BaseModel):
#     """Compares a specific attribute between two entities."""


# class CompetitionFromExternalFactors(BaseModel):
#     """Competition pressure arising from external factors."""


# class ConditionsForSuccessfulGreenManureApplication(BaseModel):
#     """Conditions required for successful green manure application."""


# class ConsumptionRelation(BaseModel):
#     """Consumption relation (who/what consumes what)."""


# class ContainMannequins(BaseModel):
#     """Container/space contains mannequins (alternate naming variant)."""


# class ContainsOrHasPart(BaseModel):
#     """Entity contains or has a part/component/sub-entity."""


# class ContainsTrench(BaseModel):
#     """Entity contains a trench (structure/layout element)."""


# class CoveredOrProtectedWithMaterials(BaseModel):
#     """Entity covered or protected using specific materials."""


# class CropRelatedInfo(BaseModel):
#     """General crop-related information association."""


# class DiffersFrom(BaseModel):
#     """Entity differs from another entity (general differs-from relation)."""


# class EdgeCreation(BaseModel):
#     """Meta: edge creation event/record (provenance for relation creation)."""


# class ExposureEffectOnDevelopment(BaseModel):
#     """Effect of exposure (sun/wind/etc.) on development."""


# class ExtensionRelationship(BaseModel):
#     """Extension/expansion relationship between entities."""


# class FearOfPests(BaseModel):
#     """Fear response specifically directed toward pests."""


# class Follows(BaseModel):
#     """Temporal/sequence relation: one event/practice follows another."""


# class GrowInWinter(BaseModel):
#     """Entity grows in winter / winter-growing association."""


# class GrowthRateRelationship(BaseModel):
#     """Relationship describing/affecting growth rate."""


# class GrowthStageRelatedTo(BaseModel):
#     """Links an entity to something related to a growth stage."""


# class HairConditionFavorableForGrowth(BaseModel):
#     """Condition of hair/structure that favors growth (domain-specific)."""


# class HasCostlyAspect(BaseModel):
#     """Entity has a costly aspect/cost driver."""


# class HasDimensionalProperty(BaseModel):
#     """Entity has a dimensional property (size/length/height/etc.)."""


# class HasPuttyOrPulley(BaseModel):
#     """Entity has putty or pulley (structural/mechanical feature)."""


# class HasRelationshipWith(BaseModel):
#     """Generic relationship holder: entity has a relationship with another."""


# class HasStructuralTimbers(BaseModel):
#     """Entity has structural timbers (construction element)."""


# class HeatRelatedInteraction(BaseModel):
#     """Interaction related to heat (heat effect/transfer/response)."""


# class HypernymOf(BaseModel):
#     """Entity is a hypernym (broader term) of another entity."""


# class IntermarriagePattern(BaseModel):
#     """Pattern of intermarriage (social/anthropological relation)."""


# class LettuceNeverReplaced(BaseModel):
#     """Constraint/statement: lettuce is never replaced (domain-specific)."""


# class LettuceRelationship(BaseModel):
#     """General lettuce-related relationship."""


# class LocatedInOrAt(BaseModel):
#     """Entity located in or at a place (generalized spatial relation)."""


# class LocatedInParis(BaseModel):
#     """Entity located in Paris (special-case/location tag)."""


# class LocationAssociation(BaseModel):
#     """General association to a location (non-specific location link)."""


# class MarketingRelation(BaseModel):
#     """Marketing-related association for an entity."""


# class MilledToBleach(BaseModel):
#     """Entity milled/processed to bleach/whiten (processing purpose)."""


# class MonthlyTiming(BaseModel):
#     """Timing information indicating a monthly schedule."""


# class MulchRelated(BaseModel):
#     """General mulch-related relationship."""


# class NativeOrigin(BaseModel):
#     """Native origin of an entity (where it is native to)."""


# class NegativeAssociation(BaseModel):
#     """Negative association between entities (inhibitory/undesirable link)."""


# class NegativelyAffectsGrowth(BaseModel):
#     """Entity negatively affects growth of another entity."""


# class OccupiesSpaceOf(BaseModel):
#     """Entity occupies the space of another entity (spatial replacement/overlap)."""


# class OrientationRelationship(BaseModel):
#     """Orientation relationship (directional/oriented relative to something)."""


# class PartOf(BaseModel):
#     """Entity is part of a larger whole (part-of relation)."""


# class PeasCultivationPractices(BaseModel):
#     """Practices associated with peas cultivation (domain-specific)."""


# class PlantabilityStatus(BaseModel):
#     """Status indicating whether something is plantable / planting readiness."""


# class PlantedIn(BaseModel):
#     """Planting location/container: entity planted in something."""


# class PlantingOrHarvestingMethod(BaseModel):
#     """Method used for planting or harvesting."""


# class PracticesInOrRelatedTo(BaseModel):
#     """Entity practices in or is related to a context/domain/location."""


# class ProductionRelation(BaseModel):
#     """Production relationship (general production link)."""


# class ProneToDegeneration(BaseModel):
#     """Entity prone to degeneration (alternate naming variant)."""


# class PruneOrCut(BaseModel):
#     """Pruning or cutting action relation."""


# class RaisedOrEnhancedAt(BaseModel):
#     """Attribute/state raised or enhanced at a time/place/condition."""


# class ReceivedBy(BaseModel):
#     """Entity received by another (recipient relation)."""


# class RelatedToEconomicInformation(BaseModel):
#     """Entity related to economic information (alternate naming variant)."""


# class RelatedToFarmingPractice(BaseModel):
#     """Entity related to a farming practice (domain link)."""


# class Removed(BaseModel):
#     """Entity removed (general removal event/link)."""


# class RentsAt(BaseModel):
#     """Entity rents at a location/context (rental relation variant)."""


# class RequiresConditionalRemoval(BaseModel):
#     """Requires removal under specific conditions."""


# class ResearchInitiation(BaseModel):
#     """Research initiation event/association."""


# class RetainsSeedViabilityFor(BaseModel):
#     """Seed retains viability for a specified duration."""


# class SeasonAssociatedEvents(BaseModel):
#     """Events associated with a season."""


# class SeasonalChervilActivity(BaseModel):
#     """Seasonal activity related to chervil (domain-specific)."""


# class SeasonalRelatedness(BaseModel):
#     """General seasonal relatedness association."""


# class SeedingRelatedState(BaseModel):
#     """State/condition related to seeding stage."""


# class SeparatedBy(BaseModel):
#     """Entities separated by a boundary/feature/constraint."""


# class SoilConditionReasonsForNoTransplanting(BaseModel):
#     """Soil-condition reasons explaining no-transplanting decision."""


# class SpreadBy(BaseModel):
#     """Entity spread/transmitted by another (vector/spread mechanism)."""


# class SproutsFromOrIn(BaseModel):
#     """Entity sprouts from or in a location/substrate."""


# class TemporalAssociation(BaseModel):
#     """General temporal association between entities/events."""


# class ThinningMethodOrTool(BaseModel):
#     """Thinning method or tool used."""


# class TimestampCreated(BaseModel):
#     """Timestamp indicating when an entity/edge was created."""


# class TransportationRelation(BaseModel):
#     """Transportation relationship (how something is transported)."""


# class TreatedWithSomething(BaseModel):
#     """Treatment relation variant: treated with some agent/input/practice."""


# class UncertainOrDifficultToDetermine(BaseModel):
#     """Marks a relation/value as uncertain or difficult to determine."""


# class UsedWithOrBy(BaseModel):
#     """Usage relation variant: used with or used by."""


# class VarietyOf(BaseModel):
#     """Entity is a variety of another entity (taxonomy/variety relation)."""


# class WateringRelation(BaseModel):
#     """Watering/irrigation relation variant (watering specifically)."""


# class YieldingInto(BaseModel):
#     """Yield/output yielding into a container/stream/result (output destination)."""

# edge_types = {
#     "AccessibilityDifference": AccessibilityDifference,
#     "AffectedBy": AffectedBy,
#     "AgriculturalTechnique": AgriculturalTechnique,
#     "AlsoKnownByName": AlsoKnownByName,
#     "AlternativeOrReplacement": AlternativeOrReplacement,
#     "AppealRenewal": AppealRenewal,
#     "AsparagusColorVariety": AsparagusColorVariety,
#     "AssignedTo": AssignedTo,
#     "AssociatedWith": AssociatedWith,
#     "AttachedWith": AttachedWith,
#     "AttendeeOfEvent": AttendeeOfEvent,
#     "AvailableAtLocation": AvailableAtLocation,
#     "AwardedForFounding": AwardedForFounding,
#     "BearsFoodIn": BearsFoodIn,
#     "BellTimingInfo": BellTimingInfo,
#     "BlanchingPurpose": BlanchingPurpose,
#     "BlanchingSource": BlanchingSource,
#     "BuriedInGround": BuriedInGround,
#     "CabbageHarvestingTime": CabbageHarvestingTime,
#     "CarrotContainerRelation": CarrotContainerRelation,
#     "CategoryRelationship": CategoryRelationship,
#     "CauseOf": CauseOf,
#     "Causes": Causes,
#     "CompareTo": CompareTo,
#     "ComparesTo": ComparesTo,
#     "CompetitionStatus": CompetitionStatus,
#     "CompetitivePressureFromExternalFactors": CompetitivePressureFromExternalFactors,
#     "ConditionallyTriggered": ConditionallyTriggered,
#     "ConditionsForSuccessfulOverwintering": ConditionsForSuccessfulOverwintering,
#     "ConstructingWindbreaks": ConstructingWindbreaks,
#     "ConsumerOf": ConsumerOf,
#     "Containment": Containment,
#     "ContainmentIssue": ContainmentIssue,
#     "ContainmentLocation": ContainmentLocation,
#     "Contains": Contains,
#     "ContainsMannequins": ContainsMannequins,
#     "ContainsPaths": ContainsPaths,
#     "CreationTime": CreationTime,
#     "CropCharacteristic": CropCharacteristic,
#     "CultivatedTaxonomyRelationship": CultivatedTaxonomyRelationship,
#     "DeficiencyRelationship": DeficiencyRelationship,
#     "DependentOn": DependentOn,
#     "DiffersFromEntity": DiffersFromEntity,
#     "DuplicateTranslation": DuplicateTranslation,
#     "EarlierThan": EarlierThan,
#     "EarlyHarvest": EarlyHarvest,
#     "EdgeAssociation": EdgeAssociation,
#     "ElevatedBy": ElevatedBy,
#     "Endogamy": Endogamy,
#     "EquipmentRelationship": EquipmentRelationship,
#     "ExemptFromSubstitution": ExemptFromSubstitution,
#     "ExemptFromTransplanting": ExemptFromTransplanting,
#     "FamilyRelationship": FamilyRelationship,
#     "FarmEquipmentRelationship": FarmEquipmentRelationship,
#     "FearResponse": FearResponse,
#     "FinancialExchange": FinancialExchange,
#     "FoundingDate": FoundingDate,
#     "FrameAssociation": FrameAssociation,
#     # "GeneratesOutput": GeneratesOutput,
#     "GerminationContext": GerminationContext,
#     "GrowBelowGround": GrowBelowGround,
#     "GrownIn": GrownIn,
#     "GrowthStageRelation": GrowthStageRelation,
#     "HairConduceiveToGrowth": HairConduceiveToGrowth,
#     "HarvestedAt": HarvestedAt,
#     "HasAssociatedEntity": HasAssociatedEntity,
#     "HasCharacteristic": HasCharacteristic,
#     "HasDimensionalAttribute": HasDimensionalAttribute,
#     "HasDimensionalReach": HasDimensionalReach,
#     "HasHighMaintenanceRequirement": HasHighMaintenanceRequirement,
#     "HasMonetaryValue": HasMonetaryValue,
#     "HasStructuralElements": HasStructuralElements,
#     "HeatTransferRelationship": HeatTransferRelationship,
#     "HighQuality": HighQuality,
#     "Hypernymy": Hypernymy,
#     "ImpactOnDevelopment": ImpactOnDevelopment,
#     "InhibitsDevelopment": InhibitsDevelopment,
#     "InstanceOf": InstanceOf,
#     "IrrigationRelation": IrrigationRelation,
#     "IsRelevantTo": IsRelevantTo,
#     "LayeringRelationship": LayeringRelationship,
#     "LeadPipeMaterialOrAlternative": LeadPipeMaterialOrAlternative,
#     "LeftInPlace": LeftInPlace,
#     "LettuceTypeAssociation": LettuceTypeAssociation,
#     "LimitationRelationship": LimitationRelationship,
#     "LocatedIn": LocatedIn,
#     "LocationRelationship": LocationRelationship,
#     "ManagedByOrganizationOrTeam": ManagedByOrganizationOrTeam,
#     "ManureRelated": ManureRelated,
#     "MarketingRelationship": MarketingRelationship,
#     "MarketGardenerCharacteristics": MarketGardenerCharacteristics,
#     "MarketGardeningRelated": MarketGardeningRelated,
#     "MaturityDateRelation": MaturityDateRelation,
#     "MeasurementRelation": MeasurementRelation,
#     "MembershipRelationship": MembershipRelationship,
#     "MilledToFinish": MilledToFinish,
#     "MonthlyComparisonOfSuccess": MonthlyComparisonOfSuccess,
#     "MonthlyOccurrence": MonthlyOccurrence,
#     "MovedTo": MovedTo,
#     "MulchRelation": MulchRelation,
#     "NotGrown": NotGrown,
#     "NotRelatedTo": NotRelatedTo,
#     "OccursAt": OccursAt,
#     "OptionalRelationship": OptionalRelationship,
#     "OriginatesFrom": OriginatesFrom,
#     "OverlapsWith": OverlapsWith,
#     "PartOfRelationship": PartOfRelationship,
#     "PeopleRelationshipEconomicActivity": PeopleRelationshipEconomicActivity,
#     "PilesInWetlands": PilesInWetlands,
#     "PlantableStatus": PlantableStatus,
#     "PlantedAt": PlantedAt,
#     "PlantingRelationship": PlantingRelationship,
#     "PoliceActionAffects": PoliceActionAffects,
#     "PracticeOf": PracticeOf,
#     "Precedes": Precedes,
#     "PreferredCondition": PreferredCondition,
#     "PreparationStatus": PreparationStatus,
#     "Produces": Produces,
#     "ProducesGuideFor": ProducesGuideFor,
#     "ProducesOutput": ProducesOutput,
#     "PropagationMethod": PropagationMethod,
#     "PropagationSource": PropagationSource,
#     "ProtectedOrCoveredWithMaterials": ProtectedOrCoveredWithMaterials,
#     "ProtectionRelation": ProtectionRelation,
#     "ProtectsFrom": ProtectsFrom,
#     "ProneToDegradation": ProneToDegradation,
#     "PruneRelation": PruneRelation,
#     "RadishOrigin": RadishOrigin,
#     "RateOfChange": RateOfChange,
#     "ReceiverOf": ReceiverOf,
#     "RegionSpecific": RegionSpecific,
#     "RelatedToFinancialInformation": RelatedToFinancialInformation,
#     "RelatedToGardenLocations": RelatedToGardenLocations,
#     "RelatedToGreens": RelatedToGreens,
#     "RemovalRelation": RemovalRelation,
#     "RemovableInSunlight": RemovableInSunlight,
#     "RemovedFrom": RemovedFrom,
#     "RentalLocation": RentalLocation,
#     "RepositionsObjects": RepositionsObjects,
#     "Requirement": Requirement,
#     "Requires": Requires,
#     "ResistantTo": ResistantTo,
#     "RetainsViabilityFor": RetainsViabilityFor,
#     "SeasonalAssociation": SeasonalAssociation,
#     "SeasonalPattern": SeasonalPattern,
#     "SeedingRelatedDestruction": SeedingRelatedDestruction,
#     "SeedingRelationship": SeedingRelationship,
#     "SelectedOrPicked": SelectedOrPicked,
#     # "SeparatedIntoOrBy": SeparatedIntoOrBy,
#     "SequenceRelationship": SequenceRelationship,
#     "SimilarityRelationship": SimilarityRelationship,
#     "SoilRelationship": SoilRelationship,
#     "SourceOfOrigins": SourceOfOrigins,
#     "SouthOriented": SouthOriented,
#     "SpatialRelationship": SpatialRelationship,
#     "SproutsFromLocation": SproutsFromLocation,
#     "StartedInvestigation": StartedInvestigation,
#     "ThinningTechnique": ThinningTechnique,
#     "TimeRelationship": TimeRelationship,
#     "TransplantationEvent": TransplantationEvent,
#     "TransportationMethod": TransportationMethod,
#     "TreatedBy": TreatedBy,
#     "TreatedWith": TreatedWith,
#     # "UncertainOrDifficultToDetermine": UncertainOrDifficultToDetermine,
#     "UsedWithPeas": UsedWithPeas,
#     "Uses": Uses,
#     "UtilizedInContextOf": UtilizedInContextOf,
#     "VariationOf": VariationOf,
#     "VisualRepresentation": VisualRepresentation,
#     "WeatherSensitivity": WeatherSensitivity,
#     "AffectedByAuthorityAction": AffectedByAuthorityAction,
#     "AimedAtProducingResourceFor": AimedAtProducingResourceFor,
#     "AlsoKnownAs": AlsoKnownAs,
#     "AssociatedWithOrganizationOrPersonnel": AssociatedWithOrganizationOrPersonnel,
#     "AttendeeOfReligiousEvent": AttendeeOfReligiousEvent,
#     "AvailableInLocation": AvailableInLocation,
#     "AwardedPrize": AwardedPrize,
#     "BasedOn": BasedOn,
#     "BeforeRipeningOnVine": BeforeRipeningOnVine,
#     "BellRelatedInfo": BellRelatedInfo,
#     "BlanchingBoundary": BlanchingBoundary,
#     "CabbageHarvestingAge": CabbageHarvestingAge,
#     "CarrotIsLocatedInOrOn": CarrotIsLocatedInOrOn,
#     "CategoryOf": CategoryOf,
#     "CollarPosition": CollarPosition,
#     "CompareAttribute": CompareAttribute,
#     "CompetitionFromExternalFactors": CompetitionFromExternalFactors,
#     "ConditionsForSuccessfulGreenManureApplication": ConditionsForSuccessfulGreenManureApplication,
#     "ConsumptionRelation": ConsumptionRelation,
#     "ContainMannequins": ContainMannequins,
#     "ContainsOrHasPart": ContainsOrHasPart,
#     "ContainsTrench": ContainsTrench,
#     "CoveredOrProtectedWithMaterials": CoveredOrProtectedWithMaterials,
#     "CropRelatedInfo": CropRelatedInfo,
#     "DiffersFrom": DiffersFrom,
#     "EdgeCreation": EdgeCreation,
#     "ExposureEffectOnDevelopment": ExposureEffectOnDevelopment,
#     "ExtensionRelationship": ExtensionRelationship,
#     "FearOfPests": FearOfPests,
#     "Follows": Follows,
#     "GrowInWinter": GrowInWinter,
#     "GrowthRateRelationship": GrowthRateRelationship,
#     "GrowthStageRelatedTo": GrowthStageRelatedTo,
#     "HairConditionFavorableForGrowth": HairConditionFavorableForGrowth,
#     "HasCostlyAspect": HasCostlyAspect,
#     "HasDimensionalProperty": HasDimensionalProperty,
#     "HasPuttyOrPulley": HasPuttyOrPulley,
#     "HasRelationshipWith": HasRelationshipWith,
#     "HasStructuralTimbers": HasStructuralTimbers,
#     "HeatRelatedInteraction": HeatRelatedInteraction,
#     "HypernymOf": HypernymOf,
#     "IntermarriagePattern": IntermarriagePattern,
#     "LettuceNeverReplaced": LettuceNeverReplaced,
#     "LettuceRelationship": LettuceRelationship,
#     "LocatedInOrAt": LocatedInOrAt,
#     "LocatedInParis": LocatedInParis,
#     "LocationAssociation": LocationAssociation,
#     "MarketingRelation": MarketingRelation,
#     "MilledToBleach": MilledToBleach,
#     "MonthlyTiming": MonthlyTiming,
#     "MulchRelated": MulchRelated,
#     "NativeOrigin": NativeOrigin,
#     "NegativeAssociation": NegativeAssociation,
#     "NegativelyAffectsGrowth": NegativelyAffectsGrowth,
#     "OccupiesSpaceOf": OccupiesSpaceOf,
#     "OrientationRelationship": OrientationRelationship,
#     "PartOf": PartOf,
#     "PeasCultivationPractices": PeasCultivationPractices,
#     "PlantabilityStatus": PlantabilityStatus,
#     "PlantedIn": PlantedIn,
#     "PlantingOrHarvestingMethod": PlantingOrHarvestingMethod,
#     "PracticesInOrRelatedTo": PracticesInOrRelatedTo,
#     "ProductionRelation": ProductionRelation,
#     "ProneToDegeneration": ProneToDegeneration,
#     "PruneOrCut": PruneOrCut,
#     "RaisedOrEnhancedAt": RaisedOrEnhancedAt,
#     "ReceivedBy": ReceivedBy,
#     "RelatedToEconomicInformation": RelatedToEconomicInformation,
#     "RelatedToFarmingPractice": RelatedToFarmingPractice,
#     "Removed": Removed,
#     "RentsAt": RentsAt,
#     "RequiresConditionalRemoval": RequiresConditionalRemoval,
#     "ResearchInitiation": ResearchInitiation,
#     "RetainsSeedViabilityFor": RetainsSeedViabilityFor,
#     "SeasonAssociatedEvents": SeasonAssociatedEvents,
#     "SeasonalChervilActivity": SeasonalChervilActivity,
#     "SeasonalRelatedness": SeasonalRelatedness,
#     "SeedingRelatedState": SeedingRelatedState,
#     "SeparatedBy": SeparatedBy,
#     "SoilConditionReasonsForNoTransplanting": SoilConditionReasonsForNoTransplanting,
#     "SpreadBy": SpreadBy,
#     "SproutsFromOrIn": SproutsFromOrIn,
#     "TemporalAssociation": TemporalAssociation,
#     "ThinningMethodOrTool": ThinningMethodOrTool,
#     "TimestampCreated": TimestampCreated,
#     "TransportationRelation": TransportationRelation,
#     "TreatedWithSomething": TreatedWithSomething,
#     "UncertainOrDifficultToDetermine": UncertainOrDifficultToDetermine,
#     "UsedWithOrBy": UsedWithOrBy,
#     "VarietyOf": VarietyOf,
#     "WateringRelation": WateringRelation,
#     "YieldingInto": YieldingInto,
# }

# # edge_types = {
# #     "PlantedAt": PlantedAt,
# #     "HarvestedAt": HarvestedAt,
# #     "GrownIn": GrownIn,
# #     "AffectedBy": AffectedBy,
# #     "TreatedWith": TreatedWith,
# #     "Requires": Requires,
# #     "Uses": Uses,
# #     "Prefers": Prefers,
# #     "Contains": Contains,
# #     "OccursAt": OccursAt,
# #     "Precedes": Precedes,
# #     "Produces": Produces,
# #     "ProtectsFrom": ProtectsFrom,
# #     "LocatedIn": LocatedIn,
# #     "CauseOf": CauseOf,
# # }
