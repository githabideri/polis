# Testing Harness Example Outputs

Snapshot taken during live test run.

- Date: 2026-01-12
- Additional samples: 2026-01-13 (block selection, context goto, error response, bot LOS activate, interact command, inventory give/drop/pickup)
- Commit: c1bae34
- Mod version: 0.1.0
- Player: the player
- Player UID (URL-encode `+` as `%2B` in query params): d4pJ+Ty1RgaBHrQgQEV8z27E

## Endpoints

### GET /polis/status
Response:
```json
{
  "ok": true,
  "harness": {
    "running": true,
    "port": 8585
  },
  "server": {
    "runPhase": "RunGame",
    "worldReady": true
  },
  "timeMs": 1693556,
  "modVersion": "0.1.0"
}
```

### GET /polis/players
Response:
```json
{
  "ok": true,
  "players": [
    {
      "uid": "d4pJ+Ty1RgaBHrQgQEV8z27E",
      "name": "the player",
      "pos": [
        228.69818115234375,
        3.00006103515625,
        258.06585693359375
      ],
      "yaw": 0.07714844,
      "pitch": 3.2041016,
      "eyePos": [
        228.69818115234375,
        4.70006103515625,
        258.06585693359375
      ],
      "dimension": 0
    }
  ]
}
```

### GET /polis/player?uid=d4pJ%2BTy1RgaBHrQgQEV8z27E
Response:
```json
{
  "uid": "d4pJ+Ty1RgaBHrQgQEV8z27E",
  "name": "the player",
  "pos": [
    228.69818115234375,
    3.00006103515625,
    258.06585693359375
  ],
  "yaw": 0.07714844,
  "pitch": 3.2041016,
  "eyePos": [
    228.69818115234375,
    4.70006103515625,
    258.06585693359375
  ],
  "dimension": 0
}
```

### GET /polis/look?uid=d4pJ%2BTy1RgaBHrQgQEV8z27E
Response:
```json
{
  "ok": true,
  "lookVec": [
    0.0769214,
    -0.06246821,
    0.99507827
  ],
  "blockSelection": null,
  "entitySelection": {
    "id": 160,
    "code": "game:playerbot",
    "pos": [
      229.1851782816656,
      3.0001,
      261.7242487609642
    ],
    "face": "north",
    "hit": [
      -0.2273871865146475,
      1.4891306643575315,
      -0.30000001192092896
    ]
  }
}
```

Example (block hit):
```json
{
  "ok": true,
  "lookVec": [
    -0.12048011,
    -0.5108229,
    0.8512018
  ],
  "blockSelection": {
    "pos": [
      228,
      2,
      260
    ],
    "face": "up",
    "hit": [
      228.29721332514194,
      3,
      260.89872716892063
    ],
    "code": "game:soil-medium-normal"
  },
  "entitySelection": null
}
```

### GET /polis/targets?playerUid=d4pJ%2BTy1RgaBHrQgQEV8z27E&radius=6&limit=10&mode=blocks
Response:
```json
{
  "Ok": true,
  "Center": [
    228.2093505859375,
    3.00006103515625,
    262.0784912109375
  ],
  "Radius": 6,
  "Blocks": [
    {
      "Pos": [
        228,
        2,
        262
      ],
      "Code": "game:soil-medium-normal",
      "Dist": 0.72,
      "EntityClass": null,
      "PlacedPriorityInteract": false,
      "Behaviors": [
        "BlockBehaviorMyceliumHost",
        "BlockBehaviorReinforcable"
      ],
      "Reasons": [
        "BlockBehaviors"
      ]
    }
  ],
  "Entities": []
}
```

### GET /polis/targets?playerUid=d4pJ%2BTy1RgaBHrQgQEV8z27E&radius=6&limit=10&mode=entities
Response:
```json
{
  "Ok": true,
  "Center": [
    228.2093505859375,
    3.00006103515625,
    262.0784912109375
  ],
  "Radius": 6,
  "Blocks": [],
  "Entities": [
    {
      "Id": 189,
      "Code": "game:playerbot",
      "Class": "EntityPlayerBot",
      "Pos": [
        228.59869384765625,
        3.0001,
        259.06085205078125
      ],
      "Dist": 3.04
    }
  ]
}
```

### GET /polis/targets?playerUid=d4pJ%2BTy1RgaBHrQgQEV8z27E&radius=6&limit=200&mode=blocks (chair/door/chest nearby)
Response (trimmed to relevant entries):
```json
{
  "Ok": true,
  "Center": [
    224.4129638671875,
    3.00006103515625,
    271.23992919921875
  ],
  "Radius": 6,
  "Blocks": [
    {
      "Pos": [
        224,
        3,
        270
      ],
      "Code": "game:chest-east",
      "Dist": 0.9,
      "EntityClass": "GenericTypedContainer",
      "PlacedPriorityInteract": false,
      "Behaviors": [
        "BlockBehaviorLockable",
        "BlockBehaviorContainer",
        "BlockBehaviorCarryableInteract",
        "BlockBehaviorCarryable",
        "BlockBehaviorReinforcable"
      ],
      "Reasons": [
        "EntityClass",
        "BlockBehaviors"
      ]
    },
    {
      "Pos": [
        223,
        3,
        268
      ],
      "Code": "game:door-solid-oak",
      "Dist": 2.93,
      "EntityClass": "Generic",
      "PlacedPriorityInteract": false,
      "Behaviors": [
        "BlockBehaviorLockable",
        "BlockBehaviorDoor",
        "BlockBehaviorBlockEntityInteract",
        "BlockBehaviorCarryableInteract",
        "BlockBehaviorReinforcable"
      ],
      "Reasons": [
        "EntityClass",
        "BlockBehaviors"
      ]
    },
    {
      "Pos": [
        224,
        3,
        267
      ],
      "Code": "game:chair-plain",
      "Dist": 3.77,
      "EntityClass": null,
      "PlacedPriorityInteract": false,
      "Behaviors": [
        "BlockBehaviorUnstableFalling",
        "BlockBehaviorReinforcable"
      ],
      "Reasons": [
        "BlockBehaviors"
      ]
    }
  ],
  "Entities": []
}
```

## Inventory Give/Drop/Pickup (2026-01-13)

### POST /polis/command (give)
```json
{
  "Ok": true,
  "Message": "Gave 10x game:stone-granite to bot #232",
  "Data": null
}
```

### GET /polis/state?botId=232 (after give)
```json
{
  "Bot": {
    "Id": 232,
    "Pos": [
      229.739013671875,
      3.0001,
      276.43988037109375
    ],
    "RightHand": {
      "Code": "game:blade-blackguard-iron",
      "Qty": 1
    },
    "LeftHand": {
      "Code": "game:stone-granite",
      "Qty": 10
    },
    "Backpack": null
  },
  "Items": [],
  "LastAction": null,
  "LastActionMs": 0,
  "LastActionId": 0,
  "Error": null
}
```

### POST /polis/command (drop)
```json
{
  "Ok": true,
  "Message": "dropped 2x game:stone-granite",
  "Data": null
}
```

### GET /polis/state?botId=232&radius=20 (after drop)
```json
{
  "Bot": {
    "Id": 232,
    "Pos": [
      226.48888568630073,
      3.0001,
      267.82844959783256
    ],
    "RightHand": {
      "Code": "game:blade-blackguard-iron",
      "Qty": 1
    },
    "LeftHand": null,
    "Backpack": null
  },
  "Items": [
    {
      "Id": 235,
      "Code": "game:stone-granite",
      "Qty": 2,
      "Dist": 2.81
    }
  ],
  "LastAction": {
    "Name": "drop",
    "Ok": true,
    "Msg": "dropped 2x game:stone-granite"
  },
  "LastActionMs": 337807,
  "LastActionId": 5,
  "Error": null
}
```

### POST /polis/command (pickup)
```json
{
  "Ok": true,
  "Message": "picked 2x game:stone-granite from #235",
  "Data": null
}
```

### GET /polis/state?botId=232 (after pickup)
```json
{
  "Bot": {
    "Id": 232,
    "Pos": [
      226.48888568630073,
      3.0001,
      267.82844959783256
    ],
    "RightHand": {
      "Code": "game:blade-blackguard-iron",
      "Qty": 1
    },
    "LeftHand": {
      "Code": "game:stone-granite",
      "Qty": 2
    },
    "Backpack": null
  },
  "Items": [],
  "LastAction": {
    "Name": "pickup",
    "Ok": true,
    "Msg": "picked 2x game:stone-granite from #235"
  },
  "LastActionMs": 350634,
  "LastActionId": 6,
  "Error": null
}
```

### GET /polis/targets?playerUid=d4pJ%2BTy1RgaBHrQgQEV8z27E&radius=6&limit=20&mode=blocks&requireEntityClass=true&codeContains=chest,door
Response:
```json
{
  "Ok": true,
  "Center": [
    224.96697998046875,
    3.00006103515625,
    271.72979736328125
  ],
  "Radius": 6,
  "Blocks": [
    {
      "Pos": [
        224,
        3,
        270
      ],
      "Code": "game:chest-east",
      "Dist": 1.41,
      "EntityClass": "GenericTypedContainer",
      "PlacedPriorityInteract": false,
      "Behaviors": [
        "BlockBehaviorLockable",
        "BlockBehaviorContainer",
        "BlockBehaviorCarryableInteract",
        "BlockBehaviorCarryable",
        "BlockBehaviorReinforcable"
      ],
      "Reasons": [
        "EntityClass",
        "BlockBehaviors"
      ]
    },
    {
      "Pos": [
        223,
        3,
        268
      ],
      "Code": "game:door-solid-oak",
      "Dist": 3.58,
      "EntityClass": "Generic",
      "PlacedPriorityInteract": false,
      "Behaviors": [
        "BlockBehaviorLockable",
        "BlockBehaviorDoor",
        "BlockBehaviorBlockEntityInteract",
        "BlockBehaviorCarryableInteract",
        "BlockBehaviorReinforcable"
      ],
      "Reasons": [
        "EntityClass",
        "BlockBehaviors"
      ]
    }
  ],
  "Entities": []
}
```

### GET /polis/targets?botId=191&radius=6&limit=20&mode=blocks&q=chest
Response:
```json
{
  "Ok": true,
  "Center": [
    224.49187330574776,
    3.0001,
    269.3790022207
  ],
  "Radius": 6,
  "Blocks": [
    {
      "Pos": [
        224,
        3,
        270
      ],
      "Code": "game:chest-east",
      "Dist": 1.23,
      "EntityClass": "GenericTypedContainer",
      "PlacedPriorityInteract": false,
      "Behaviors": [
        "BlockBehaviorLockable",
        "BlockBehaviorContainer",
        "BlockBehaviorCarryableInteract",
        "BlockBehaviorCarryable",
        "BlockBehaviorReinforcable"
      ],
      "Reasons": [
        "EntityClass",
        "BlockBehaviors"
      ]
    }
  ],
  "Entities": []
}
```

### GET /polis/targets?botId=191&radius=6&limit=20&mode=entities&q=stone
Response:
```json
{
  "Ok": true,
  "Center": [
    224.49187330574776,
    3.0001,
    269.3790022207
  ],
  "Radius": 6,
  "Blocks": [],
  "Entities": [
    {
      "Id": 195,
      "Code": "game:item",
      "Class": "EntityItem",
      "Pos": [
        226.1991751540966,
        3.0001,
        270.1986360804114
      ],
      "Dist": 1.89,
      "ItemCode": "game:stone-granite",
      "ItemQty": 1
    }
  ]
}
```

### GET /polis/targets?playerUid=d4pJ%2BTy1RgaBHrQgQEV8z27E&radius=8&limit=50&mode=entities (corpse nearby)
Response (trimmed):
```json
{
  "Ok": true,
  "Entities": [
    {
      "Id": 197,
      "Code": "playercorpse:playercorpse",
      "Class": "EntityPlayerCorpse",
      "Pos": [
        227.5,
        3.0001,
        267.5
      ],
      "Dist": 6.08,
      "ItemCode": null,
      "ItemQty": null
    }
  ]
}
```

### POST /polis/servercmd (/polis interact while aiming at corpse)
Response:
```json
{
  "ok": true,
  "status": "Success",
  "message": "Interact started",
  "errorCode": null,
  "data": null
}
```

### GET /polis/targets?botId=191&radius=8&limit=5&mode=blocks&q=bush
Response:
```json
{
  "Ok": true,
  "Center": [
    227.6052320909105,
    3.0001,
    271.5498618057085
  ],
  "Radius": 8,
  "Blocks": [
    {
      "Pos": [
        229,
        3,
        274
      ],
      "Code": "game:bigberrybush-redcurrant-ripe",
      "Dist": 3.54,
      "EntityClass": "BerryBush",
      "PlacedPriorityInteract": false,
      "Behaviors": [
        "BlockBehaviorHarvestable",
        "HarvestMarkerBehavior",
        "BlockBehaviorReinforcable"
      ],
      "Reasons": [
        "EntityClass",
        "BlockBehaviors"
      ]
    }
  ],
  "Entities": []
}
```

### POST /polis/command (activate berry bush by coords)
Response:
```json
{
  "Ok": true,
  "Message": "Bot #191 activating block at 229, 3, 274",
  "Data": null
}
```

### GET /polis/state (after berry bush activate)
Response:
```json
{
  "Bot": {
    "Id": 191,
    "Pos": [
      229.44325350317214,
      3.0001,
      273.39959224956334
    ],
    "RightHand": {
      "Code": "game:stone-granite",
      "Qty": 1
    },
    "LeftHand": null
  },
  "Items": [],
  "LastAction": {
    "Name": "activate",
    "Ok": true,
    "Msg": "handled"
  },
  "LastActionMs": 1972173,
  "LastActionId": 4,
  "Error": null
}
```

### GET /polis/look?uid=d4pJ%2BTy1RgaBHrQgQEV8z27E (chair aim)
Response:
```json
{
  "ok": true,
  "lookVec": [
    0.11755021,
    -0.26063588,
    -0.95825404
  ],
  "blockSelection": {
    "pos": [
      224,
      3,
      267
    ],
    "face": "up",
    "hit": [
      224.89783052591045,
      3.625,
      267.28735916519634
    ],
    "code": "game:chair-plain"
  },
  "entitySelection": null
}
```

### GET /polis/bots
Response:
```json
{
  "Ok": true,
  "Message": "11 bot(s) found",
  "Data": {
    "bots": [
      {
        "id": 161,
        "code": "game:playerbot",
        "pos": [
          228.16034792261945,
          3.0001,
          262.74677670971647
        ],
        "lastAction": {
          "name": "goto",
          "ok": true,
          "msg": "done",
          "id": 1,
          "ms": 534408
        }
      },
      {
        "id": 160,
        "code": "game:playerbot",
        "pos": [
          229.1851782816656,
          3.0001,
          261.7242487609642
        ],
        "lastAction": {
          "name": "goto",
          "ok": true,
          "msg": "done",
          "id": 1,
          "ms": 534684
        }
      },
      {
        "id": 154,
        "code": "game:playerbot",
        "pos": [
          231.11542090059032,
          3.0001,
          270.29719912963634
        ],
        "lastAction": {
          "name": "goto",
          "ok": true,
          "msg": "done",
          "id": 1,
          "ms": 535315
        }
      },
      {
        "id": 147,
        "code": "game:playerbot",
        "pos": [
          231.58310358838293,
          3.0001,
          273.0332922303066
        ],
        "lastAction": {
          "name": "goto",
          "ok": true,
          "msg": "done",
          "id": 1,
          "ms": 536419
        }
      },
      {
        "id": 145,
        "code": "game:playerbot",
        "pos": [
          224.4759699004159,
          3.0001,
          276.1593051805084
        ],
        "lastAction": {
          "name": "goto",
          "ok": true,
          "msg": "done",
          "id": 1,
          "ms": 535673
        }
      },
      {
        "id": 142,
        "code": "game:playerbot",
        "pos": [
          237.38588935979695,
          3.0001,
          279.8660762718761
        ],
        "lastAction": {
          "name": "goto",
          "ok": true,
          "msg": "done",
          "id": 1,
          "ms": 535248
        }
      },
      {
        "id": 156,
        "code": "game:playerbot",
        "pos": [
          151.5184031121253,
          3.0001,
          168.49065761806304
        ],
        "lastAction": {
          "name": "goto",
          "ok": true,
          "msg": "done",
          "id": 1,
          "ms": 535449
        }
      },
      {
        "id": 158,
        "code": "game:playerbot",
        "pos": [
          -28,
          3,
          18
        ],
        "lastAction": {
          "name": "goto",
          "ok": false,
          "msg": "stuck",
          "id": 1,
          "ms": 536015
        }
      },
      {
        "id": 159,
        "code": "game:playerbot",
        "pos": [
          -28,
          6,
          16
        ],
        "lastAction": {
          "name": "goto",
          "ok": false,
          "msg": "stuck",
          "id": 1,
          "ms": 536150
        }
      },
      {
        "id": 163,
        "code": "game:playerbot",
        "pos": [
          228.66409475398927,
          3.0001,
          263.5491929702236
        ],
        "lastAction": {
          "name": "goto",
          "ok": true,
          "msg": "done",
          "id": 2,
          "ms": 535808
        }
      },
      {
        "id": 176,
        "code": "game:playerbot",
        "pos": [
          228.69818115234375,
          3.0001,
          260.06585693359375
        ],
        "lastAction": {
          "name": "pickup",
          "ok": false,
          "msg": "inventory full, nothing transferred",
          "id": 2,
          "ms": 1695462
        }
      }
    ]
  }
}
```

### POST /polis/command (activate by coords)
Response:
```json
{
  "Ok": true,
  "Message": "Bot #191 activating block at 230, 2, 281",
  "Data": null
}
```

### GET /polis/state (after activate)
Response:
```json
{
  "Bot": {
    "Id": 191,
    "Pos": [
      230.35764727406595,
      3.0001,
      281.4927036571363
    ],
    "RightHand": {
      "Code": "game:blade-blackguard-iron",
      "Qty": 1
    },
    "LeftHand": null
  },
  "Items": [],
  "LastAction": {
    "Name": "activate",
    "Ok": true,
    "Msg": "activated"
  },
  "LastActionMs": 223963,
  "LastActionId": 1,
  "Error": null
}
```

### POST /polis/command (activate door by coords)
Response:
```json
{
  "Ok": true,
  "Message": "Bot #191 activating block at 223, 3, 268",
  "Data": null
}
```

### GET /polis/state (after door activate)
Response:
```json
{
  "Bot": {
    "Id": 191,
    "Pos": [
      223.56735816937385,
      3.0001,
      267.44129777791505
    ],
    "RightHand": {
      "Code": "game:blade-blackguard-iron",
      "Qty": 1
    },
    "LeftHand": null
  },
  "Items": [],
  "LastAction": {
    "Name": "activate",
    "Ok": true,
    "Msg": "handled"
  },
  "LastActionMs": 963127,
  "LastActionId": 2,
  "Error": null
}
```

### POST /polis/command (activate chair by look target)
Response:
```json
{
  "Ok": true,
  "Message": "Bot #191 activating block at 224, 3, 267",
  "Data": null
}
```

### GET /polis/state (after chair activate)
Response:
```json
{
  "Bot": {
    "Id": 191,
    "Pos": [
      223.4796534970068,
      3.0001,
      268.5748999880791
    ],
    "RightHand": {
      "Code": "game:blade-blackguard-iron",
      "Qty": 1
    },
    "LeftHand": null
  },
  "Items": [],
  "LastAction": {
    "Name": "activate",
    "Ok": true,
    "Msg": "activated"
  },
  "LastActionMs": 1625433,
  "LastActionId": 4,
  "Error": null
}
```

### POST /polis/command (activate chest by coords)
Response:
```json
{
  "Ok": true,
  "Message": "Bot #191 activating block at 224, 3, 270",
  "Data": null
}
```

### GET /polis/state (after chest activate)
Response:
```json
{
  "Bot": {
    "Id": 191,
    "Pos": [
      224.49187330574776,
      3.0001,
      269.3790022207
    ],
    "RightHand": {
      "Code": "game:blade-blackguard-iron",
      "Qty": 1
    },
    "LeftHand": null
  },
  "Items": [],
  "LastAction": {
    "Name": "activate",
    "Ok": true,
    "Msg": "handled"
  },
  "LastActionMs": 1641650,
  "LastActionId": 5,
  "Error": null
}
```

## Commands

All commands are `POST /polis/command` with a JSON body. Responses below are from the same run as the endpoint samples above.

### spawn
Request:
```json
{
  "cmd": "spawn",
  "context": {
    "playerUid": "d4pJ+Ty1RgaBHrQgQEV8z27E",
    "spawnOffset": [0, 0, 2]
  }
}
```
Response:
```json
{
  "Ok": true,
  "Message": "Spawned bot #176 (playerbot)",
  "Data": {
    "id": 176,
    "code": "playerbot",
    "pos": [
      228.69818115234375,
      3.00006103515625,
      260.06585693359375
    ]
  }
}
```

### select
Request:
```json
{
  "cmd": "select",
  "args": ["176"]
}
```
Response:
```json
{
  "Ok": true,
  "Message": "Selected bot #176",
  "Data": null
}
```

### select (invalid id)
Request:
```json
{
  "cmd": "select",
  "args": ["999999"]
}
```
Response:
```json
{
  "Ok": false,
  "Message": "Bot 999999 not found",
  "Data": null
}
```

### selectlook
Request:
```json
{
  "cmd": "selectlook",
  "context": {
    "playerUid": "d4pJ+Ty1RgaBHrQgQEV8z27E"
  }
}
```
Response:
```json
{
  "Ok": true,
  "Message": "Selected bot #176",
  "Data": null
}
```

### give
Request:
```json
{
  "cmd": "give",
  "args": ["game:stone-granite", "2"]
}
```
Response:
```json
{
  "Ok": true,
  "Message": "Gave 2x game:stone-granite to bot #176",
  "Data": null
}
```

### drop
Request:
```json
{
  "cmd": "drop",
  "args": ["-1", "1"]
}
```
Response:
```json
{
  "Ok": true,
  "Message": "dropped 1x game:stone-granite",
  "Data": null
}
```

### pickup
Request:
```json
{
  "cmd": "pickup"
}
```
Response (failure in this run):
```json
{
  "Ok": false,
  "Message": "inventory full, nothing transferred",
  "Data": null
}
```

### pickup (too fresh)
Request:
```json
{
  "cmd": "pickup",
  "args": ["184", "8"]
}
```
Response (failure in this run):
```json
{
  "Ok": false,
  "Message": "CanCollect returned false for entity 184",
  "Data": null
}
```

### pickup (inventory full or no valid slots)
Request:
```json
{
  "cmd": "pickup",
  "args": ["269"]
}
```
Response (failure in this run):
```json
{
  "Ok": false,
  "Message": "inventory full or no valid slots",
  "Data": null
}
```

### pickup (out of range)
Request:
```json
{
  "cmd": "pickup",
  "args": ["282"]
}
```
Response (failure in this run):
```json
{
  "Ok": false,
  "Message": "out of range dist=4.66 range=3.00",
  "Data": null
}
```

### pickup (no item nearby)
Request:
```json
{
  "cmd": "pickup"
}
```
Response (failure in this run):
```json
{
  "Ok": false,
  "Message": "No item entity found nearby",
  "Data": null
}
```

### goto
Request:
```json
{
  "cmd": "goto",
  "args": ["230.69818115234375", "3.00006103515625", "258.06585693359375"]
}
```
Response:
```json
{
  "Ok": true,
  "Message": "Bot #176 moving to (230.7, 3.0, 258.1)",
  "Data": null
}
```

### goto (context offset)
Request:
```json
{
  "cmd": "goto",
  "context": {
    "playerUid": "d4pJ+Ty1RgaBHrQgQEV8z27E",
    "gotoOffset": [0, 0, 2]
  }
}
```
Response:
```json
{
  "Ok": true,
  "Message": "Bot #180 moving to (228.7, 3.0, 260.1)",
  "Data": null
}
```

### gotolook
Request:
```json
{
  "cmd": "gotolook",
  "context": {
    "playerUid": "d4pJ+Ty1RgaBHrQgQEV8z27E"
  }
}
```
Response:
```json
{
  "Ok": true,
  "Message": "Bot #176 moving to (232.4, 1.7, 305.8)",
  "Data": null
}
```

### stop
Request:
```json
{
  "cmd": "stop"
}
```
Response:
```json
{
  "Ok": true,
  "Message": "Stopped bot #176",
  "Data": null
}
```

### teststate
Request:
```json
{
  "cmd": "teststate"
}
```
Response:
```json
{
  "Ok": true,
  "Message": "State retrieved",
  "Data": {
    "Bot": {
      "Id": 161,
      "Pos": [
        228.16034792261945,
        3.0001,
        262.74677670971647
      ],
      "RightHand": {
        "Code": "game:blade-blackguard-iron",
        "Qty": 1
      },
      "LeftHand": {
        "Code": "game:stone-granite",
        "Qty": 1
      }
    },
    "Items": [
      {
        "Id": 175,
        "Code": "game:blade-blackguard-iron",
        "Qty": 1,
        "Dist": 1.83
      },
      {
        "Id": 169,
        "Code": "game:stone-granite",
        "Qty": 2,
        "Dist": 3.53
      },
      {
        "Id": 173,
        "Code": "game:blade-blackguard-iron",
        "Qty": 1,
        "Dist": 4.22
      }
    ],
    "LastAction": {
      "Name": "goto",
      "Ok": true,
      "Msg": "done"
    },
    "LastActionMs": 534408,
    "LastActionId": 1,
    "Error": null
  }
}
```

### bots
Request:
```json
{
  "cmd": "bots"
}
```
Response:
```json
{
  "Ok": true,
  "Message": "11 bot(s) found",
  "Data": {
    "bots": [
      {
        "id": 161,
        "code": "game:playerbot",
        "pos": [
          228.16034792261945,
          3.0001,
          262.74677670971647
        ],
        "lastAction": {
          "name": "goto",
          "ok": true,
          "msg": "done",
          "id": 1,
          "ms": 534408
        }
      },
      {
        "id": 160,
        "code": "game:playerbot",
        "pos": [
          229.1851782816656,
          3.0001,
          261.7242487609642
        ],
        "lastAction": {
          "name": "goto",
          "ok": true,
          "msg": "done",
          "id": 1,
          "ms": 534684
        }
      }
    ]
  }
}
```

### despawn
Request:
```json
{
  "cmd": "despawn"
}
```
Response:
```json
{
  "Ok": true,
  "Message": "Despawned bot #176",
  "Data": null
}
```

## Server Command Examples

### POST /polis/servercmd (missing player)
Request:
```json
{
  "cmd": "/weather set clearsky"
}
```
Response:
```json
{
  "ok": false,
  "status": "Error",
  "message": "Caller must be player",
  "errorCode": "",
  "data": null
}
```

### POST /polis/servercmd (with player)
Request:
```json
{
  "cmd": "/weather set clearsky",
  "playerUid": "d4pJ+Ty1RgaBHrQgQEV8z27E"
}
```
Response:
```json
{
  "ok": true,
  "status": "Success",
  "message": "Ok weather pattern set for all loaded regions",
  "errorCode": null,
  "data": null
}
```

### POST /polis/servercmd (time query)
Request:
```json
{
  "cmd": "/time",
  "playerUid": "d4pJ+Ty1RgaBHrQgQEV8z27E"
}
```
Response:
```json
{
  "ok": true,
  "status": "Success",
  "message": "Server time: 7. June, Year 0, 16:09\\nGame Speed: 48 IRL minutes",
  "errorCode": null,
  "data": null
}
```

### POST /polis/servercmd (player entity)
Request:
```json
{
  "cmd": "/player the player entity",
  "playerUid": "d4pJ+Ty1RgaBHrQgQEV8z27E"
}
```
Response:
```json
{
  "ok": true,
  "status": "Success",
  "message": "Position: x=228.69818115234375, y=3.00006103515625, z=258.06585693359375, Satiety: 750/1500, Health: 15/15",
  "errorCode": null,
  "data": null
}
```

## State Snapshots

### GET /polis/state?botId=176&radius=6 (after drop)
```json
{
  "Bot": {
    "Id": 176,
    "Pos": [
      228.69818115234375,
      3.0001,
      260.06585693359375
    ],
    "RightHand": {
      "Code": "game:stone-granite",
      "Qty": 1
    },
    "LeftHand": null
  },
  "Items": [
    {
      "Id": 173,
      "Code": "game:blade-blackguard-iron",
      "Qty": 1,
      "Dist": 1.74
    },
    {
      "Id": 169,
      "Code": "game:stone-granite",
      "Qty": 2,
      "Dist": 1.79
    },
    {
      "Id": 175,
      "Code": "game:blade-blackguard-iron",
      "Qty": 1,
      "Dist": 2.42
    }
  ],
  "LastAction": {
    "Name": "drop",
    "Ok": true,
    "Msg": "dropped 1x game:stone-granite"
  },
  "LastActionMs": 1693910,
  "LastActionId": 1,
  "Error": null
}
```

### GET /polis/state?botId=176&radius=6 (after pickup attempt)
```json
{
  "Bot": {
    "Id": 176,
    "Pos": [
      228.69818115234375,
      3.0001,
      260.06585693359375
    ],
    "RightHand": {
      "Code": "game:stone-granite",
      "Qty": 1
    },
    "LeftHand": {
      "Code": "game:blade-blackguard-iron",
      "Qty": 1
    }
  },
  "Items": [
    {
      "Id": 173,
      "Code": "game:blade-blackguard-iron",
      "Qty": 1,
      "Dist": 1.74
    },
    {
      "Id": 169,
      "Code": "game:stone-granite",
      "Qty": 2,
      "Dist": 1.79
    },
    {
      "Id": 175,
      "Code": "game:blade-blackguard-iron",
      "Qty": 1,
      "Dist": 2.42
    }
  ],
  "LastAction": {
    "Name": "pickup",
    "Ok": false,
    "Msg": "inventory full, nothing transferred"
  },
  "LastActionMs": 1695462,
  "LastActionId": 2,
  "Error": null
}
```

## Item Tracking (via /polis/state)

There is no global `/polis/items` endpoint. Use `/polis/state?botId=...&radius=...` and track item `Dist` changes to watch drops in motion.

Example samples after a drop (0.5s intervals, same bot):
```json
{
  "samples": [
    {
      "t": 0,
      "items": [
        {"Id": 179, "Code": "game:stone-granite", "Qty": 1, "Dist": 1.25},
        {"Id": 178, "Code": "game:stone-granite", "Qty": 1, "Dist": 2.15},
        {"Id": 173, "Code": "game:blade-blackguard-iron", "Qty": 1, "Dist": 2.89}
      ]
    },
    {
      "t": 1,
      "items": [
        {"Id": 178, "Code": "game:stone-granite", "Qty": 1, "Dist": 2.15},
        {"Id": 173, "Code": "game:blade-blackguard-iron", "Qty": 1, "Dist": 2.89},
        {"Id": 179, "Code": "game:stone-granite", "Qty": 1, "Dist": 3.38}
      ]
    },
    {
      "t": 2,
      "items": [
        {"Id": 178, "Code": "game:stone-granite", "Qty": 1, "Dist": 2.15},
        {"Id": 179, "Code": "game:stone-granite", "Qty": 1, "Dist": 2.74},
        {"Id": 173, "Code": "game:blade-blackguard-iron", "Qty": 1, "Dist": 2.89}
      ]
    }
  ]
}
```

### POST /polis/command (activate door by coords, bot LOS fail)
Response:
```json
{
  "Ok": false,
  "Message": "No line of sight to target.",
  "Data": null
}
```

### POST /polis/command (activate chest by coords, bot LOS pass)
Response:
```json
{
  "Ok": true,
  "Message": "Bot #191 activating block at 224, 3, 270",
  "Data": null
}
```

### POST /polis/command (interact entity by id)
Response:
```json
{
  "Ok": true,
  "Message": "Bot #191 interacting with entity 197 (mode=Interact)",
  "Data": null
}
```

### GET /polis/state?botId=191 (after interact)
Response:
```json
{
  "Bot": {
    "Id": 191,
    "Pos": [
      227.42409117286724,
      3.0001,
      267.39916871371514
    ],
    "RightHand": {
      "Code": "game:stone-granite",
      "Qty": 1
    },
    "LeftHand": null
  },
  "Items": [],
  "LastAction": {
    "Name": "activate",
    "Ok": true,
    "Msg": "handled"
  },
  "LastActionMs": 2054063,
  "LastActionId": 6,
  "Error": null
}
```

### GET /polis/targets?playerUid=d4pJ%2BTy1RgaBHrQgQEV8z27E&radius=12&limit=200&mode=blocks&q=lantern
Response:
```json
{
  "Ok": true,
  "Center": [
    227.6644287109375,
    3.49530029296875,
    274.10064697265625
  ],
  "Radius": 12,
  "Blocks": [
    {
      "Pos": [
        223,
        4,
        272
      ],
      "Code": "game:lantern-south",
      "Dist": 4.57,
      "EntityClass": "Lantern",
      "PlacedPriorityInteract": false,
      "Behaviors": [
        "BlockBehaviorLockable",
        "BlockBehaviorOmniAttachable",
        "BlockBehaviorRightClickPickup",
        "BlockBehaviorReinforcable"
      ],
      "Reasons": [
        "EntityClass",
        "BlockBehaviors"
      ]
    }
  ],
  "Entities": []
}
```

### GET /polis/targets?playerUid=d4pJ%2BTy1RgaBHrQgQEV8z27E&radius=12&limit=200&mode=blocks&q=barrel
Response:
```json
{
  "Ok": true,
  "Center": [
    227.6644287109375,
    3.49530029296875,
    274.10064697265625
  ],
  "Radius": 12,
  "Blocks": [
    {
      "Pos": [
        229,
        3,
        268
      ],
      "Code": "game:barrel",
      "Dist": 5.89,
      "EntityClass": "Barrel",
      "PlacedPriorityInteract": false,
      "Behaviors": [
        "BlockBehaviorLockable",
        "BlockBehaviorUnstableFalling",
        "BlockBehaviorCarryableInteract",
        "BlockBehaviorCarryable",
        "BlockBehaviorReinforcable"
      ],
      "Reasons": [
        "EntityClass",
        "BlockBehaviors"
      ]
    }
  ],
  "Entities": []
}
```

### GET /polis/targets?playerUid=d4pJ%2BTy1RgaBHrQgQEV8z27E&radius=12&limit=200&mode=blocks&q=gate
Response:
```json
{
  "Ok": true,
  "Center": [
    227.6644287109375,
    3.49530029296875,
    274.10064697265625
  ],
  "Radius": 12,
  "Blocks": [
    {
      "Pos": [
        227,
        3,
        265
      ],
      "Code": "game:wattlegate-sticks-n-closed-left-free",
      "Dist": 8.6,
      "EntityClass": null,
      "PlacedPriorityInteract": false,
      "Behaviors": [
        "BlockBehaviorLockable",
        "BlockBehaviorReinforcable"
      ],
      "Reasons": [
        "BlockBehaviors"
      ]
    }
  ],
  "Entities": []
}
```

### GET /polis/targets?playerUid=d4pJ%2BTy1RgaBHrQgQEV8z27E&radius=12&limit=200&mode=blocks&q=groundstorage
Response:
```json
{
  "Ok": true,
  "Center": [
    227.6644287109375,
    3.49530029296875,
    274.10064697265625
  ],
  "Radius": 12,
  "Blocks": [
    {
      "Pos": [
        224,
        3,
        269
      ],
      "Code": "game:groundstorage",
      "Dist": 5.58,
      "EntityClass": "GroundStorage",
      "PlacedPriorityInteract": false,
      "Behaviors": [
        "BlockBehaviorLockable",
        "BlockBehaviorUnstableFalling",
        "BlockBehaviorReinforcable"
      ],
      "Reasons": [
        "EntityClass",
        "BlockBehaviors"
      ]
    }
  ],
  "Entities": []
}
```

### POST /polis/command (activate lantern by coords, LOS fail)
Response:
```json
{
  "Ok": false,
  "Message": "No line of sight to target.",
  "Data": null
}
```

### POST /polis/command (activate barrel by coords)
Response:
```json
{
  "Ok": true,
  "Message": "Bot #191 activating block at 229, 3, 268",
  "Data": null
}
```

### POST /polis/command (activate gate by coords)
Response:
```json
{
  "Ok": true,
  "Message": "Bot #191 activating block at 227, 3, 265",
  "Data": null
}
```

### POST /polis/command (activate groundstorage by coords)
Response:
```json
{
  "Ok": true,
  "Message": "Bot #191 activating block at 224, 3, 269",
  "Data": null
}
```

### GET /polis/targets?botId=191&radius=12&limit=200&mode=blocks&q=lantern
Response:
```json
{
  "Ok": true,
  "Center": [
    230.77841974561105,
    3.0001,
    276.2024102040141
  ],
  "Radius": 12,
  "Blocks": [
    {
      "Pos": [
        223,
        4,
        272
      ],
      "Code": "game:lantern-south",
      "Dist": 8.3,
      "EntityClass": "Lantern",
      "PlacedPriorityInteract": false,
      "Behaviors": [
        "BlockBehaviorLockable",
        "BlockBehaviorOmniAttachable",
        "BlockBehaviorRightClickPickup",
        "BlockBehaviorReinforcable"
      ],
      "Reasons": [
        "EntityClass",
        "BlockBehaviors"
      ]
    }
  ],
  "Entities": []
}
```

### GET /polis/targets?botId=191&radius=12&limit=200&mode=blocks&q=quern
Response (trimmed):
```json
{
  "Ok": true,
  "Blocks": [
    {
      "Pos": [
        229,
        3,
        272
      ],
      "Code": "game:quern-granite",
      "EntityClass": "Quern"
    }
  ]
}
```

### GET /polis/targets?botId=191&radius=12&limit=200&mode=blocks&q=vessel
Response (trimmed):
```json
{
  "Ok": true,
  "Blocks": [
    {
      "Pos": [
        226,
        3,
        273
      ],
      "Code": "game:storagevessel-red-fired",
      "EntityClass": "GenericTypedContainer"
    }
  ]
}
```

### GET /polis/targets?botId=191&radius=12&limit=200&mode=blocks&q=anvil
Response (trimmed):
```json
{
  "Ok": true,
  "Blocks": [
    {
      "Pos": [
        229,
        3,
        271
      ],
      "Code": "game:anvil-steel",
      "EntityClass": "Anvil"
    }
  ]
}
```

### GET /polis/targets?botId=191&radius=12&limit=200&mode=blocks&q=gate
Response (trimmed):
```json
{
  "Ok": true,
  "Blocks": [
    {
      "Pos": [
        227,
        3,
        265
      ],
      "Code": "game:wattlegate-sticks-n-closed-left-free"
    }
  ]
}
```

### GET /polis/targets?botId=191&radius=12&limit=200&mode=blocks&q=groundstorage
Response (trimmed):
```json
{
  "Ok": true,
  "Blocks": [
    {
      "Pos": [
        224,
        3,
        269
      ],
      "Code": "game:groundstorage",
      "EntityClass": "GroundStorage"
    }
  ]
}
```

### GET /polis/targets?botId=191&radius=16&limit=200&mode=blocks&q=lever
Response:
```json
{
  "Ok": true,
  "Center": [
    230.77841974561105,
    3.0001,
    276.2024102040141
  ],
  "Radius": 16,
  "Blocks": [],
  "Entities": []
}
```

### GET /polis/targets?botId=191&radius=12&limit=200&mode=blocks&q=valve
Response:
```json
{
  "Ok": true,
  "Center": [
    232.61173429171967,
    3.0001,
    277.82902400488945
  ],
  "Radius": 12,
  "Blocks": [
    {
      "Pos": [
        227,
        3,
        273
      ],
      "Code": "game:jonas-steamengine-valve1-west",
      "Dist": 6.72,
      "EntityClass": "Generic",
      "PlacedPriorityInteract": false,
      "Behaviors": [
        "BlockBehaviorHorizontalOrientable",
        "BlockBehaviorReinforcable"
      ],
      "Reasons": [
        "EntityClass",
        "BlockBehaviors"
      ]
    }
  ],
  "Entities": []
}
```

### POST /polis/command (activate lantern by coords after reposition)
Response:
```json
{
  "Ok": true,
  "Message": "Bot #191 activating block at 223, 4, 272",
  "Data": null
}
```

### POST /polis/command (activate quern)
Response:
```json
{
  "Ok": true,
  "Message": "Bot #191 activating block at 229, 3, 272",
  "Data": null
}
```

### POST /polis/command (activate storage vessel)
Response:
```json
{
  "Ok": true,
  "Message": "Bot #191 activating block at 226, 3, 273",
  "Data": null
}
```

### POST /polis/command (activate anvil)
Response:
```json
{
  "Ok": true,
  "Message": "Bot #191 activating block at 229, 3, 271",
  "Data": null
}
```

### POST /polis/command (activate wattle gate twice)
Response:
```json
{
  "Ok": true,
  "Message": "Bot #191 activating block at 227, 3, 265",
  "Data": null
}
```

### POST /polis/command (activate valve lever, initial LOS fail)
Response:
```json
{
  "Ok": false,
  "Message": "No line of sight to target.",
  "Data": null
}
```

### POST /polis/command (activate valve lever after reposition)
Response:
```json
{
  "Ok": true,
  "Message": "Bot #191 activating block at 227, 3, 273",
  "Data": null
}
```

### POST /polis/command (activate lantern twice to test toggle)
Response:
```json
{
  "Ok": true,
  "Message": "Bot #191 activating block at 223, 4, 272",
  "Data": null
}
```

## Notes

- `GET /polis/look` uses `uid` as the query param and requires URL encoding. `playerUid` is only for command `context` bodies.
- Pickup can fail with `inventory full, nothing transferred` even after a drop. This is an inventory limitation, not a harness failure.
- Pickup can also fail with `CanCollect returned false` for about ~1s after an item spawns; wait before retrying.
- Dropped items can leave the bot radius quickly (initial velocity). If `/polis/state` shows no `Items` after a drop, increase the radius or sample quickly.
- Item tracking is distance-only from the selected bot; there is no absolute position or velocity in the response today.
- `activate` LOS failures only show in the command response; `LastAction` may remain from a previous action.
- Firewood placed on the ground appeared as `game:groundstorage` (block entity). `/polis/targets` does not expose the contents of ground storage, so `q=firewood` does not match.
- Lever was not detected within a 16-block bot scan using `q=lever` or `codeContains=lever`. The “Iron pipe valve trip lever” shows as `game:jonas-steamengine-valve1-west` and is discoverable via `q=valve`.
- Lantern activation does **not** toggle the light on/off (observed in-game).
