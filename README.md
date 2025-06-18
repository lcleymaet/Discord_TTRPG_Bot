# Discord_TTRPG_Bot
A bot made to store and assist with playing TTRPG's through Discord. Currently in early development and not deployed on any servers.

## Current functionality:
- Roll dice! This command allows anybody in a server where this bot lives to roll dice using NdM notation. Supports up to 50 dice at a time to prevent spam.
- Play a slot machine - Permits a player to play a slot machine-esque game from the discord chat. Commands are set up in a tree to guide player to correct functionality
- Initializes a sqlite database on bot startup if none exists. This is a relational databse that stores user data that can be linked to any number of D&D 5e characters. 
- - Weapons table is initialized and will need to be populated with weapon names and the dice used to roll it. This is functionality planned for far future

## Future plans
- Switch to a Postgresql database for fast remote access to player data so this can scale more easily. Plans for the data is to be used as a personal project in a machine learning algorithm to be able to determine different PC characteristics from other characteristics.
- Add ability for players to call their characters and roll stat checks
- Add weapon roll functionality
- Conduct tests to tune slot machine game to a certain expected ROI over time
- Add class resource tracking (spell slots, action surge, sorcery points etc)
- Add subclass support outside of what is in player's handbook (and Tasha's for artificer class)
