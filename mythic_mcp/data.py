"""Fate Chart values transcribed from assistant.zip / MainActivity.java."""
ODDS = [
    "Impossible", "No way", "Very unlikely", "Unlikely", "50/50",
    "Somewhat likely", "Likely", "Very likely", "Near sure thing",
    "A sure thing", "Has to be",
]
YES_CHANCES = {
    "Impossible":       [-20, 0, 0, 5, 5, 10, 15, 25, 50],
    "No way":           [0, 5, 5, 10, 15, 25, 35, 50, 75],
    "Very unlikely":    [5, 5, 10, 15, 25, 45, 50, 65, 85],
    "Unlikely":         [5, 10, 15, 20, 35, 50, 55, 75, 90],
    "50/50":            [10, 15, 25, 35, 50, 65, 75, 85, 95],
    "Somewhat likely":  [20, 25, 45, 50, 65, 80, 85, 90, 95],
    "Likely":           [25, 35, 50, 55, 75, 85, 90, 95, 100],
    "Very likely":      [45, 50, 65, 75, 85, 90, 95, 95, 105],
    "Near sure thing":  [50, 55, 75, 80, 90, 95, 95, 100, 115],
    "A sure thing":     [55, 65, 80, 85, 90, 95, 95, 110, 125],
    "Has to be":        [80, 85, 90, 95, 95, 100, 100, 130, 145],
}

def java_int_div(numerator: int, denominator: int) -> int:
    """Java integer division truncates toward zero; Python // floors negatives."""
    return abs(numerator) // denominator * (1 if numerator >= 0 else -1)

def fate_thresholds(yes_chance: int) -> tuple[int, int]:
    """Match the source app's rollFateChart() arithmetic exactly."""
    exceptional_yes = java_int_div(yes_chance, 5)
    exceptional_no = 100 - java_int_div(100 - yes_chance, 5) + 1
    return exceptional_yes, exceptional_no

# These meaning tables are supplied as a convenience transcription from the
# prior project draft. Check against the exact licensed Mythic edition if exact
# wording/order is important; they were not present in assistant.zip's Java/XML.
ACTION_MEANINGS = [
"Attainment","Starting","Neglect","Fighting","Recruit","Triumph","Violate","Oppose","Malice","Communicate",
"Pursue","Increase","Decrease","Abandon","Gratify","Inquire","Antagonize","Move","Waste","Truce",
"Release","Befriend","Judge","Desert","Control","Delay","Praise","Separate","Take","Break",
"Heal","Delay","Stop","Lie","Return","Imitate","Struggle","Inform","Bestow","Postpone",
"Reveal","Bargain","Imprison","Release","Celebrate","Develop","Travel","Block","Harm","Humiliate",
"Extravagance","Postponement","Difficulty","Kill","Disrupt","Usurp","Create","Betray","Agree","Abuse",
"Oppress","Inspect","Ambush","Spy","Attach/Connect","Carry/Transport","Open","Carelessness","Ruin","Extravagance",
"Deceive/Trick","Arrive","Propose","Divide","Refuse","Distrust","Deceive","Cruelty","Impatience","Trust",
"Excitement","Activity","Assist","Care","Negligence","Passion","Work hard","Control","Attract","Fail",
"Pursue","Vengeance","Proceed/Process","Dispute","Punish","Guide","Transform","Overthrow","Oppress","Change",
]
SUBJECT_MEANINGS = [
"Goals","Dreams","Environment","Outside","Inside","Reality","Allies","Enemies","Evil","Good",
"Emotions","Resistance","War","Peace","Innocence","Love","Spirituality","Intellect","New Ideas","Joy",
"Messages","Energy","Balance","Tension","Friendship","Physical","Project","Pleasures","Pain","Possessions",
"Benefits","Plans","Lies","Expectations","Legal Matters","Bureaucracy","Business","Path","News","Exterior Factors",
"Advice","Plans/Conspiracy","Competition","Prison","Illness","Food","Attention","Success","Failure","Travel",
"Jealousy","Argument","Home","Investment","Suffering","Wishes","Tactics","Stalemate","Randomness","Misfortune",
"Death","Disruption","Power","Burden","Intrigues","Fears","Ambush","Rumor","Wounds","Luxury",
"Representative","Adversities","Wealth","Freedom","Military","Mundane","Trials","Masses","Vehicle","Art",
"Victory","Dispute","Riches","Status quo","Technology","Hope","Magic","Illusions","Portals","Danger",
"Weapons","Animals","Weather","Elements","Nature","Public","Leadership","Fame","Anger","Information",
]
EVENT_FOCUS = [
    (1,7,"Remote Event"), (8,28,"NPC Action"), (29,35,"Introduce a New NPC"),
    (36,45,"Move Toward a Thread"), (46,52,"Move Away from a Thread"),
    (53,55,"Close a Thread"), (56,67,"PC Negative"), (68,75,"PC Positive"),
    (76,83,"Ambiguous Event"), (84,92,"NPC Negative"), (93,100,"NPC Positive"),
]
