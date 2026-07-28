from __future__ import annotations

from cg_download.api import (
    AreaType,
    Card,
    EnergyType,
    Observation,
    Option,
    OptionType,
    PlayerState,
    Pokemon,
    SelectContext,
    SelectData,
    SelectType,
    State,
)


def card(card_id: int, serial: int, owner: int = 0) -> Card:
    return Card(id=card_id, serial=serial, playerIndex=owner)


def pokemon(
    card_id: int,
    serial: int,
    owner: int,
    *,
    hp: int = 100,
    max_hp: int = 120,
    energies: list[EnergyType] | None = None,
    energy_cards: list[Card] | None = None,
    tools: list[Card] | None = None,
    pre_evolution: list[Card] | None = None,
) -> Pokemon:
    return Pokemon(
        id=card_id,
        serial=serial,
        hp=hp,
        maxHp=max_hp,
        appearThisTurn=False,
        energies=energies or [],
        energyCards=energy_cards or [],
        tools=tools or [],
        preEvolution=pre_evolution or [],
    )


def sample_observation(*, logs=None, options=None, max_count: int = 1) -> Observation:
    my_active = pokemon(
        100,
        1,
        0,
        hp=90,
        max_hp=120,
        energies=[EnergyType.FIRE, EnergyType.FIRE, EnergyType.COLORLESS],
        energy_cards=[card(9, 20), card(1, 21)],
        tools=[card(110, 30)],
        pre_evolution=[card(90, 40)],
    )
    my_bench = pokemon(101, 2, 0)
    opp_active = pokemon(200, 3, 1, hp=70, max_hp=100)
    mine = PlayerState(
        active=[my_active],
        bench=[my_bench],
        benchMax=3,
        deckCount=48,
        discard=[card(500, 50)],
        prize=[None] * 6,
        handCount=2,
        hand=[card(300, 60), card(301, 61)],
        poisoned=True,
        burned=False,
        asleep=False,
        paralyzed=False,
        confused=False,
    )
    theirs = PlayerState(
        active=[opp_active],
        bench=[],
        benchMax=3,
        deckCount=49,
        discard=[],
        prize=[None] * 5,
        handCount=6,
        hand=None,
        poisoned=False,
        burned=False,
        asleep=False,
        paralyzed=False,
        confused=False,
    )
    current = State(
        turn=4,
        turnActionCount=3,
        yourIndex=0,
        firstPlayer=0,
        supporterPlayed=True,
        stadiumPlayed=False,
        energyAttached=True,
        retreated=False,
        result=-1,
        stadium=[card(400, 70, owner=0)],
        looking=None,
        players=[mine, theirs],
    )
    if options is None:
        options = [
            Option(type=OptionType.ATTACK, attackId=55),
            Option(
                type=OptionType.ATTACH,
                area=AreaType.HAND,
                index=0,
                playerIndex=0,
                inPlayArea=AreaType.BENCH,
                inPlayIndex=0,
            ),
            Option(
                type=OptionType.CARD,
                area=AreaType.ACTIVE,
                index=0,
                playerIndex=1,
            ),
            Option(type=OptionType.PLAY, index=1),
            Option(type=OptionType.NUMBER, number=2),
        ]
    select = SelectData(
        type=SelectType.MAIN,
        context=SelectContext.MAIN,
        minCount=1,
        maxCount=max_count,
        remainDamageCounter=4,
        remainEnergyCost=2,
        option=options,
        deck=None,
        contextCard=None,
        effect=None,
    )
    return Observation(select=select, logs=logs or [], current=current)


def sample_deck() -> list[int]:
    visible = [100, 101, 90, 9, 1, 110, 300, 301, 400, 500]
    return visible + [600] * (60 - len(visible))
