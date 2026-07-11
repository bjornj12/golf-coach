"""GraphQL query strings, built from the discovered Trackman schema.

All queries hang off the `me` root (the signed-in user). Field names are taken
verbatim from introspection — see docs/trackman-api.md.
"""

# --- Profile + current handicap -------------------------------------------
PROFILE = """
query Profile {
  me {
    profile {
      id dbId playerName fullName firstName lastName
      gender email nationality nationalityCode birthDate
      picture outdoorHandicap category dexterity
    }
    hcp {
      currentHcp
      currentRecord { hcpNew scoreDifferential adjustedGrossScore createdAt }
    }
  }
}
"""

# --- Handicap history ------------------------------------------------------
HANDICAP_HISTORY = """
query HandicapHistory($skip: Int, $take: Int, $onlyInAvg: Boolean) {
  me {
    hcp {
      currentHcp
      playerHistory(skip: $skip, take: $take, onlyInAvg: $onlyInAvg) {
        totalCount
        items {
          createdAt hcpOld hcpNew adjustedGrossScore scoreDifferential
          isInAvg adjustment
          scorecard { id course { displayName } grossScore toPar }
        }
      }
    }
  }
}
"""

# --- Sessions / activities list -------------------------------------------
LIST_SESSIONS = """
query ListSessions(
  $skip: Int, $take: Int, $kinds: [ActivityKind!],
  $timeFrom: DateTime, $timeTo: DateTime, $includeHidden: Boolean
) {
  me {
    activities(
      skip: $skip, take: $take, kinds: $kinds,
      timeFrom: $timeFrom, timeTo: $timeTo, includeHidden: $includeHidden
    ) {
      totalCount
      pageInfo { hasNextPage }
      items {
        id time kind isHidden
        ... on RangePracticeActivity {
          numberOfStrokes clubs
          location { name }
        }
        ... on CoursePlayActivity {
          gameType grossScore netScore toPar thruHole
          course { displayName }
        }
      }
    }
  }
}
"""

# --- One activity in full --------------------------------------------------
# Uses node(id:) so any activity kind resolves; inline fragments pull detail.
GET_SESSION = """
query GetSession($id: ID!) {
  node(id: $id) {
    __typename
    ... on PlayerActivity { id time kind isHidden }
    ... on RangePracticeActivity {
      id time kind numberOfStrokes clubs
      location { name }
      strokes {
        time club bayName teePosition targetPosition
        measurement {
          ballSpeed carry total carrySide totalSide
          launchAngle launchDirection landingAngle maxHeight
          ballSpin spinAxis curve hangTime distanceFromPin targetDistance
        }
      }
    }
    ... on RangeFindMyDistanceActivity {
      id time kind numberOfStrokes clubs
      location { name }
      strokes {
        time club
        measurement {
          ballSpeed carry total carrySide totalSide
          launchAngle launchDirection landingAngle ballSpin spinAxis curve
          maxHeight hangTime
        }
      }
    }
    ... on MapMyBagSessionActivity {
      id time kind strokeCount
      strokes {
        time club
        measurement {
          clubSpeed attackAngle clubPath faceAngle dynamicLoft
          ballSpeed smashFactor carry total
          launchAngle launchDirection spinRate spinAxis curve carrySide totalSide
          landingAngle maxHeight hangTime
        }
      }
    }
    ... on ShotAnalysisSessionActivity {
      id time kind strokeCount reportLink
      strokes {
        time club
        measurement {
          clubSpeed attackAngle clubPath faceAngle dynamicLoft
          ballSpeed smashFactor carry total
          launchAngle launchDirection spinRate spinAxis curve carrySide totalSide
          landingAngle maxHeight hangTime
        }
      }
    }
    ... on SimulatorSessionActivity {
      id time kind strokeCount
      strokes {
        time club
        measurement {
          clubSpeed attackAngle clubPath faceAngle dynamicLoft
          ballSpeed smashFactor carry total
          launchAngle launchDirection spinRate spinAxis curve carrySide totalSide
          landingAngle maxHeight hangTime
        }
      }
    }
    ... on VirtualRangeSessionActivity {
      id time kind strokeCount
      strokes {
        time club
        measurement {
          clubSpeed attackAngle clubPath faceAngle dynamicLoft
          ballSpeed smashFactor carry total
          launchAngle launchDirection spinRate spinAxis curve carrySide totalSide
          landingAngle maxHeight hangTime
        }
      }
    }
    ... on SessionActivity {
      id time kind strokeCount
      strokes {
        time club
        measurement {
          clubSpeed attackAngle clubPath faceAngle dynamicLoft
          ballSpeed smashFactor carry total
          launchAngle launchDirection spinRate spinAxis curve carrySide totalSide
          landingAngle maxHeight hangTime
        }
      }
    }
    ... on CoursePlayActivity {
      id time kind gameType grossScore netScore toPar thruHole
      course { displayName }
      scorecard {
        id par grossScore netScore toPar netToPar numberOfHolesPlayed isCompleted
        totalDistance courseHcp greenStimp teeName isInHcp
        course { displayName }
        stat {
          driveAverage driveMax greenInRegulation numberOfPutts
          fairwayHitFairway fairwayHitLeft fairwayHitRight
          birdies pars bogeys doubleBogeys
        }
        holes {
          holeNumber par strokeIndex distance grossScore netScore
          putts greenInRegulation hcpStrokes
          shots {
            shotNumber club total launchLie finalLie shotResult
            measurement {
              ballSpeed clubSpeed smashFactor carry total
              launchAngle launchDirection spinRate curve carrySide totalSide
              landingAngle maxHeight hangTime
            }
          }
        }
      }
    }
  }
}
"""

# --- Course rounds (scorecards) -------------------------------------------
COURSE_ROUNDS = """
query CourseRounds($skip: Int, $take: Int, $completed: Boolean) {
  me {
    scorecards(skip: $skip, take: $take, completed: $completed) {
      id createdAt startedAt finishedAt
      course { displayName }
      teeName par numberOfHolesPlayed isCompleted isInHcp
      grossScore netScore toPar outScore inScore courseHcp
      stat {
        driveAverage driveMax driveTotal driveCount highestBallSpeed
        fairwayHitFairway fairwayHitLeft fairwayHitRight
        greenInRegulation numberOfPutts averagePuttsPerHoleDecimal
        birdies pars bogeys doubleBogeys tripleBogeysOrWorse eagles
      }
      holes {
        holeNumber par strokeIndex distance grossScore netScore
        putts greenInRegulation hcpStrokes
      }
    }
  }
}
"""

# --- Club gapping / dispersion --------------------------------------------
CLUB_STATS = """
query ClubStats($includeRetired: Boolean) {
  me {
    equipment {
      clubs(includeRetired: $includeRetired) {
        id displayName isRetired
        brand { name }
        clubHead { clubHeadKind clubHeadType }
        findMyDistance {
          numberOfShots
          clubStats {
            carry total standardDeviationCarry standardDeviationTotal
          }
          dispersionCircle { centerX centerY minAxis maxAxis angle }
        }
      }
    }
  }
}
"""

# --- Full shot measurements for one session (verification) -----------------
# Bay/sim kinds expose the full Measurement type (face/path/etc.). Range kinds
# don't capture clubPath/faceAngle, but DO capture ball/launch metrics — select
# those so plans targeting e.g. carry/totalSide/curve can be graded on the range
# (the primary venue). clubPath/faceAngle targets remain bay-only by nature.
SESSION_MEASUREMENTS = """
query SessionMeasurements($id: ID!) {
  node(id: $id) {
    __typename
    ... on PlayerActivity { id time kind }
    ... on RangePracticeActivity { strokes { club measurement {
      spinAxis curve launchDirection ballSpin ballSpeed
      carry total totalSide carrySide launchAngle landingAngle maxHeight } } }
    ... on RangeFindMyDistanceActivity { strokes { club measurement {
      spinAxis curve launchDirection ballSpin ballSpeed
      carry total totalSide carrySide launchAngle landingAngle } } }
    ... on SimulatorSessionActivity { strokes { club measurement {
      clubPath faceAngle faceToPath spinAxis curve launchDirection
      spinRate ballSpeed smashFactor carry total totalSide carrySide
      attackAngle dynamicLoft } } }
    ... on ShotAnalysisSessionActivity { strokes { club measurement {
      clubPath faceAngle faceToPath spinAxis curve launchDirection
      spinRate ballSpeed smashFactor carry total totalSide carrySide
      attackAngle dynamicLoft } } }
    ... on MapMyBagSessionActivity { strokes { club measurement {
      clubPath faceAngle faceToPath spinAxis curve launchDirection
      spinRate ballSpeed smashFactor carry total totalSide carrySide
      attackAngle dynamicLoft } } }
    ... on VirtualRangeSessionActivity { strokes { club measurement {
      clubPath faceAngle faceToPath spinAxis curve launchDirection
      spinRate ballSpeed smashFactor carry total totalSide carrySide
      attackAngle dynamicLoft } } }
    ... on SessionActivity { strokes { club measurement {
      clubPath faceAngle faceToPath spinAxis curve launchDirection
      spinRate ballSpeed smashFactor carry total totalSide carrySide
      attackAngle dynamicLoft } } }
  }
}
"""

# --- Activity summary ------------------------------------------------------
ACTIVITY_SUMMARY = """
query ActivitySummary($timeFrom: DateTime, $timeTo: DateTime, $skip: Int, $take: Int) {
  me {
    activitySummary(timeFrom: $timeFrom, timeTo: $timeTo, skip: $skip, take: $take) {
      totalCount
      items { kind activityCount playerCount lastActivityTime }
    }
  }
}
"""
