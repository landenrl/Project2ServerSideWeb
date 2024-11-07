import discord
import json
import os
from discord.ext import commands
from dotenv import load_dotenv

# token so my account does not get stolen
load_dotenv
TOKEN = os.getenv('TOKEN')
intents = discord.Intents.default()
intents.messages = True
intents.message_content = True
intents.members = True

# Create bot instance
bot = commands.Bot(command_prefix='!', intents=intents)

# Global variables for queue, match data, user statistics, and match ID counter
queue = []
matches = {}
user_stats = {}
match_id_counter = 1  # Counter to track match IDs

# Load data from JSON file on startup
def load_data():
    global matches, user_stats, match_id_counter
    try:
        with open('bot_data.json', 'r') as file:
            data = json.load(file)
            matches = {int(k): v for k, v in data.get('matches', {}).items()}
            user_stats = {int(k): v for k, v in data.get('user_stats', {}).items()}
            match_id_counter = data.get('match_id_counter', 1)
            print(f"Data loaded successfully. Next match ID: {match_id_counter}")
    except FileNotFoundError:
        print("No existing data found. Starting fresh.")
    except json.JSONDecodeError:
        print("Error decoding JSON. Starting with empty data.")

# Save data to JSON file
def save_data():
    with open('bot_data.json', 'w') as file:
        data = {
            'matches': matches,
            'user_stats': user_stats,
            'match_id_counter': match_id_counter
        }
        json.dump(data, file)

@bot.event
async def on_ready():
    load_data()  # Load data when the bot starts
    print(f'Bot is online as {bot.user.name}')

@bot.command()
async def q(ctx):
    global match_id_counter
    user = ctx.author
    if user.id not in queue:
        queue.append(user.id)
        await ctx.send(f'{user.name} has joined the queue.')
    else:
        await ctx.send(f'{user.name}, you are already in the queue.')

    if len(queue) >= 2:
        player1 = queue.pop(0)
        player2 = queue.pop(0)
        matches[match_id_counter] = {'players': [player1, player2], 'reported': {}}
        await ctx.send(f'Match created! {ctx.guild.get_member(player1).name} vs {ctx.guild.get_member(player2).name}. Match ID: {match_id_counter}')
        
        match_id_counter += 1  # Increment match ID for the next match
        save_data()  # Save updated match data and match ID counter

@bot.command()
async def leave(ctx):
    user = ctx.author
    if user.id in queue:
        queue.remove(user.id)
        await ctx.send(f'{user.name} has left the queue.')
    else:
        await ctx.send(f'{user.name}, you are not currently in the queue.')

@bot.command()
async def report(ctx, match_id: int, result: str):
    user = ctx.author
    if match_id in matches:
        match = matches[match_id]
        if user.id in match['players']:
            if result.lower() not in ['w', 'l']:
                await ctx.send(f'Invalid result. Please report with "w" for win or "l" for loss.')
                return
            
            if result.lower() == 'w':
                winner = user.id
                loser = match['players'][0] if match['players'][0] != winner else match['players'][1]

                user_stats.setdefault(winner, {'wins': 0, 'losses': 0})['wins'] += 1
                user_stats.setdefault(loser, {'wins': 0, 'losses': 0})['losses'] += 1

                await ctx.send(f'Match ID {match_id} result confirmed: {user.name} wins.')
                del matches[match_id]
                save_data()  # Save updated match data and stats
            elif result.lower() == 'l':
                loser = user.id
                winner = match['players'][0] if match['players'][0] != loser else match['players'][1]

                user_stats.setdefault(winner, {'wins': 0, 'losses': 0})['wins'] += 1
                user_stats.setdefault(loser, {'wins': 0, 'losses': 0})['losses'] += 1

                await ctx.send(f'Match ID {match_id} result confirmed: {ctx.guild.get_member(winner).name} wins.')
                del matches[match_id]
                save_data()  # Save updated match data and stats
        else:
            await ctx.send(f'You are not part of Match ID {match_id}.')
    else:
        await ctx.send(f'Match ID {match_id} not found.')

@bot.command()
async def stats(ctx):
    user = ctx.author
    if user.id in user_stats:
        wins = user_stats[user.id]['wins']
        losses = user_stats[user.id]['losses']
        await ctx.send(f'{user.name}, your record: {wins} wins, {losses} losses.')
    else:
        await ctx.send(f'{user.name}, you have no recorded matches yet.')

@bot.command()
async def delete_match(ctx, match_id: int):
    if match_id in matches:
        del matches[match_id]
        save_data()  # Save updated match data
        await ctx.send(f'Match ID {match_id} has been deleted.')
    else:
        await ctx.send(f'Match ID {match_id} not found.')

@bot.command()
async def alter_winner(ctx, match_id: int, new_winner: discord.Member):
    if match_id in matches:
        match = matches[match_id]
        if new_winner.id in match['players']:
            current_winner = None
            current_loser = None
            for player_id in match['players']:
                if player_id in user_stats and user_stats[player_id]['wins'] > 0:
                    current_winner = player_id
                else:
                    current_loser = player_id

            if current_winner and current_loser:
                user_stats[current_winner]['wins'] -= 1
                user_stats[current_loser]['losses'] -= 1

            winner = new_winner.id
            loser = match['players'][0] if match['players'][0] != winner else match['players'][1]

            user_stats.setdefault(winner, {'wins': 0, 'losses': 0})['wins'] += 1
            user_stats.setdefault(loser, {'wins': 0, 'losses': 0})['losses'] += 1

            await ctx.send(f'Match ID {match_id} result has been updated: {new_winner.name} is now the winner.')
            del matches[match_id]
            save_data()  # Save updated user stats and match data
        else:
            await ctx.send(f'{new_winner.name} is not part of Match ID {match_id}.')
    else:
        await ctx.send(f'Match ID {match_id} not found.')

# Command to display the leaderboard
@bot.command()
async def leaderboards(ctx):
    if not user_stats:
        await ctx.send('No match records found.')
        return

    leaderboard = sorted(user_stats.items(), key=lambda x: x[1]['wins'], reverse=True)
    leaderboard_message = "Leaderboard:\n"
    for user_id, stats in leaderboard:
        member = ctx.guild.get_member(user_id)
        if member:
            leaderboard_message += f"{member.name}: {stats['wins']} wins, {stats['losses']} losses\n"

    await ctx.send(leaderboard_message)

# Command to reset all data
@bot.command()
async def reset_data(ctx):
    global matches, user_stats, match_id_counter
    matches.clear()
    user_stats.clear()
    match_id_counter = 1
    save_data()  # Save cleared data to file
    await ctx.send('All match data and user statistics have been reset.')

# Command to display all available commands
@bot.command()
async def commands(ctx):
    commands_list = (
        "**!q**: Join the queue and wait to be matched.\n"
        "**!leave**: Leave the queue if you are currently in it.\n"
        "**!report <match_id> <w/l>**: Report the result of a match.\n"
        "**!stats**: View your win/loss record.\n"
        "**!delete_match <match_id>**: Delete a specific match (admin use).\n"
        "**!alter_winner <match_id> @new_winner**: Change the winner of a specific match (admin use).\n"
        "**!leaderboards**: View the current leaderboard.\n"
        "**!reset_data**: Reset all match data and user statistics (admin use).\n"
        "**!commands**: Display this list of commands."
    )
    await ctx.send(f"Here are the available commands:\n{commands_list}")

# Run the bot
bot.run(TOKEN)


