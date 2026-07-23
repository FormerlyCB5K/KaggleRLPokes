# Engine Source Path Map

- Package/build/license: `README.md`, `LICENSES/`, `game.sln`, `game.vcxproj`
- Card definitions and English text: `CardImpl.h`
- Card-definition builder API: `CreateCard.h`
- Core card/skill structures: `Card.h`, `Skill.h`, `Types.h`
- Effect execution: `EffectProc.h`, `EffectInstant.h`, `EffectContinual.h`
- Conditions and targets: `SatisfyCondition.h`, `TargetList.h`, `SetProperty.h`
- Trigger processing: `PullTrigger.h`, `ActivateInfo.h`
- Game flow and selection: `GameProc.h`, `SelectProc.h`, `SetupProc.h`
- Observation/log serialization: `ToJson.h`, `ApiJson.h`, `AddLog.h`
- Public native API: `Export.cpp`, `Api.h`, `ApiData.h`
- Card/attack enumeration used for crosswalk validation: `Export.cpp::AllCard/AllAttack`
- Included tests: none

Validation uses exact source references plus focused behavior scenarios through the
installed `cg_download` simulator, as approved in `HR-B01-003`.
