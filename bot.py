#!/usr/bin/env python3

import os
import asyncio
import random
import logging

import discord
from discord.ext import commands
from dotenv import load_dotenv

logger = logging.getLogger("discord")
logger.setLevel(logging.DEBUG)
handler = logging.FileHandler(filename="discord.log", encoding="utf-8", mode="w")
handler.setFormatter(
    logging.Formatter("%(asctime)s:%(levelname)s:%(name)s: %(message)s")
)
logger.addHandler(handler)

STARTING_CARDS = 5
COLORS = ("red", "yellow", "green", "blue")
COLORS_UNICODE = (
    "\U0001F534",
    "\U0001F7E0",
    "\U0001F7E2",
    "\U0001F535",
)
COLORS_UNICODE_NAME = {
    "\U0001F534": "red",
    "\U0001F7E0": "yellow",
    "\U0001F7E2": "green",
    "\U0001F535": "blue",
}
VARIANTS = [str(c) for c in range(0, 10)] + ["reverse", "+2", "skip"]
WILD_VARIANTS = ("+4", "change_color")


class Card:
    def __init__(self, variant, color="wild"):
        self.variant = variant
        self.color = color

    def __str__(self):
        return f"{self.variant} ({self.color})"

    def __repr__(self):
        return self.__str__()

    @property
    def is_wild(self):
        return self.color == "wild"


CARDS = []
for variant in VARIANTS:
    for color in COLORS:
        CARDS.append(Card(variant, color))

for variant in WILD_VARIANTS:
    CARDS.append(Card(variant, "wild"))


class Player:
    def __init__(self, member):
        self.member = member
        self.cards = []

    def to_public_string(self):
        name = self.member.name
        no_card = len(self.cards)
        return f"{name} ({no_card} cards)"

    def to_private_string(self):
        text = ""
        for card in self.cards:
            text += str(card) + ", "
        return text

    def draw(self, k):
        cards = random.choices(CARDS, k=k)
        self.cards += cards


class GameState:
    def __init__(self, players):
        self.players = players
        self.turn = 0
        self.direction = "left"
        self.board_top = random.choice(CARDS)
        self.board_history = []

    def __getitem__(self, key):
        for player in self.players:
            if player.member.id == key:
                return player

    def is_playing(self, member):
        for player in self.players:
            if player.member.id == member.id:
                return True
        return False

    def is_turn(self, member):
        player_to_go = self.players[self.turn % len(self.players)]
        if player_to_go.member.id == member.id:
            return True
        return False

    def can_play(self, card):
        if card.is_wild:
            return True
        elif (
            self.board_top.color == card.color or self.board_top.variant == card.variant
        ):
            return True
        return False

    async def display_status(self, ctx):
        cards_status = ""
        for player in self.players:
            cards_status += player.to_public_string() + "\n"

        board_status = str(self.board_top)

        await ctx.send(cards_status + "\n" + board_status)

    async def play(self, ctx, player, card):
        print(f"{player.member.id}: play {str(card)}")
        if self.can_play(card):
            if card.variant == "change_color":
                msg = await ctx.send("Playing wild card, please react with the color")
                for reaction in COLORS_UNICODE:
                    await msg.add_reaction(reaction)

                def check(reaction, user):
                    return (
                        user == ctx.message.author
                        and str(reaction.emoji) in COLORS_UNICODE
                    )

                try:
                    reaction, user = await bot.wait_for(
                        "reaction_add", timeout=10.0, check=check
                    )
                    color_name = to_color_name(str(reaction.emoji))
                except asyncio.TimeoutError:
                    color_name = random.choice(COLORS)

                self.board_history.append(self.board_top)
                card.color = color_name
                self.board_top = card


intents = discord.Intents.default()
intents.emojis = True
intents.messages = True
intents.reactions = True

bot = commands.Bot(command_prefix="++")
bot_state = {}
game_states = []


async def get_state(member):
    for state in game_states:
        if state.is_playing(member):
            return state
    return None


def to_color_name(unicode_color):
    return COLORS_UNICODE_NAME[unicode_color]


@bot.command(help="Greeting!")
async def hello(ctx):
    await ctx.send("Hello!")


@bot.command(name="uno", help="Start an Uno game with mentioned users")
async def start_uno_game(ctx):
    state = await get_state(ctx.message.author)
    if state is not None:
        await ctx.send(
            "{}, you are already in a game".format(ctx.message.author.mention())
        )
        return

    if len(ctx.message.mentions) == 0:
        await ctx.send("Please mention user(s) that you want to play the game with")
        return

    players = []
    p = Player(ctx.author)
    p.draw(STARTING_CARDS)
    players.append(p)
    for member in ctx.message.mentions:
        p = Player(member)
        p.draw(STARTING_CARDS)
        players.append(p)

    state = GameState(players)
    game_states.append(state)

    cards_status = ""
    for player in state.players:
        cards_status += player.to_public_string() + "\n"

    board_status = str(state.board_top)

    await ctx.send(f"Welcome to the game!\n" + cards_status + "\n" + board_status)


@bot.command(name="play", help="Play the card at position n")
async def play_card(ctx, *args):
    state = await get_state(ctx.message.author)
    if state is None:
        await ctx.send("You are not in a game")
        return

    if len(args) == 0 or len(args) > 1:
        await ctx.send("Need a card position in the hand.")
        return

    if not state.is_turn(ctx.message.author):
        # TODO check for jump-in if enable.
        await ctx.send("Not your turn")
        return

    player = state[ctx.message.author.id]
    try:
        card_idx = int(args[0]) - 1
        card = player.cards.pop(card_idx)
        await state.play(ctx, player, card)
    except ValueError:
        ctx.send("Card position needs to be from {} to {}".format(1, len(player.cards)))


@bot.command(name="cards", help="Show your hand")
async def show_cards(ctx):
    state = await get_state(ctx.message.author)
    if state is None:
        await ctx.send("You are not in the game")

    player = state[ctx.message.author.id]
    await ctx.send(player.to_private_string())


@bot.command(name="uno-status")
async def get_uno_status(ctx):
    state = await get_state(ctx.message.author)
    if state is None:
        await ctx.send("You are not in the game")

    await state.display_status(ctx)


@bot.command(name="uno-give-wild", help="Give wild card to user")
async def add_wild(ctx):
    state = await get_state(ctx.message.author)
    if state is None:
        await ctx.send("You are not in the game")
    player = state[ctx.message.author.id]
    card = Card("change_color", "wild")
    player.cards.append(card)


@bot.command(name="incr", help="Increase the counter")
async def increase_counter(ctx):
    if "counter" not in bot_state:
        bot_state["counter"] = 0
    bot_state["counter"] += 1
    await ctx.send("counter increase!")


@bot.command(name="value", help="Show the counter value")
async def get_value(ctx):
    value = bot_state["counter"]
    await ctx.send(f"value is {value}")


if __name__ == "__main__":
    load_dotenv()
    token = os.getenv("DISCORD_BOT_TOKEN", "")
    bot.run(token)
