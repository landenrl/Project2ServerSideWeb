import discord
import sqlite3
import os
from discord.ext import commands
from dotenv import load_dotenv

load_dotenv()
TOKEN = os.getenv('TOKEN')
intents = discord.Intents.default()
intents.messages = True
intents.message_content = True
intents.members = True

# Create bot instance
bot = commands.Bot(command_prefix='!', intents=intents)

# In-memory queue
queue = []

# Initialize the database and create tables if they do not exist
def init_db():
    conn = sqlite3.connect('bot_data.db')
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS matches (
            match_id INTEGER PRIMARY KEY AUTOINCREMENT,
            player1_id INTEGER NOT NULL,
            player2_id INTEGER NOT NULL,
            winner_id INTEGER
        )
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS user_stats (
            user_id INTEGER PRIMARY KEY,
            wins INTEGER DEFAULT 0,
            losses INTEGER DEFAULT 0
        )
    ''')
    conn.commit()
    conn.close()

@bot.event
async def on_ready():
    init_db()  # Initialize the database
    print(f'Bot is online as {bot.user.name}')

@bot.command()
async def q(ctx):
    user = ctx.author
    if user.id not in queue:
        queue.append(user.id)
        await ctx.send(f'{user.name} has joined the queue.')
    else:
        await ctx.send(f'{user.name}, you are already in the queue.')

    # Check if there are enough players to create a match
    if len(queue) >= 2:
        player1 = queue.pop(0)
        player2 = queue.pop(0)
        winner = None

        # Debugging: Print player IDs before insertion
        print(f"DEBUG: Creating match with Player1 ID: {player1}, Player2 ID: {player2}")

        # Insert the new match into the matches table
        try:
            conn = sqlite3.connect('bot_data.db')
            c = conn.cursor()
            c.execute('INSERT INTO matches (player1_id, player2_id, winner_id) VALUES (?, ?, ?)', (player1, player2, winner))
            match_id = c.lastrowid  # Retrieve the match ID of the inserted row
            conn.commit()
            print(f"DEBUG: Match ID {match_id} created successfully")
        except sqlite3.Error as e:
            print(f"DEBUG: Error inserting match into database: {e}")
            await ctx.send("An error occurred while creating the match.")
            return
        finally:
            conn.close()

        # Notify the players
        try:
            await ctx.send(f'Match created! {ctx.guild.get_member(player1).name} vs {ctx.guild.get_member(player2).name}. Match ID: {match_id}')
        except Exception as e:
            print(f"DEBUG: Error sending match creation message: {e}")


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
    conn = sqlite3.connect('bot_data.db')
    c = conn.cursor()

    try:
        # Check if the match exists and if the user is part of it
        c.execute('SELECT player1_id, player2_id FROM matches WHERE match_id = ?', (match_id,))
        match = c.fetchone()
        if not match:
            await ctx.send(f'Match ID {match_id} does not exist.')
            return

        if user.id not in match:
            await ctx.send(f'You are not a participant in Match ID {match_id}.')
            return

        # Validate the result
        if result.lower() not in ['w', 'l']:
            await ctx.send('Invalid result. Please report with "w" for win or "l" for loss.')
            return

        # Determine winner and loser
        winner_id = user.id if result.lower() == 'w' else (match[0] if match[1] == user.id else match[1])
        loser_id = match[0] if winner_id == match[1] else match[1]

        # Update match result in the database
        c.execute('UPDATE matches SET winner_id = ? WHERE match_id = ?', (winner_id, match_id))

        # Update stats for winner
        c.execute('INSERT OR IGNORE INTO user_stats (user_id, wins, losses) VALUES (?, 0, 0)', (winner_id,))
        c.execute('UPDATE user_stats SET wins = wins + 1 WHERE user_id = ?', (winner_id,))

        # Update stats for loser
        c.execute('INSERT OR IGNORE INTO user_stats (user_id, wins, losses) VALUES (?, 0, 0)', (loser_id,))
        c.execute('UPDATE user_stats SET losses = losses + 1 WHERE user_id = ?', (loser_id,))

        conn.commit()
        await ctx.send(f'Match {match_id} has been reported. Winner: {ctx.guild.get_member(winner_id).name}.')
    except sqlite3.Error as e:
        print(f"DEBUG: Error updating match result: {e}")
        await ctx.send('An error occurred while reporting the match.')
    finally:
        conn.close()


@bot.command()
async def stats(ctx):
    user = ctx.author
    conn = sqlite3.connect('bot_data.db')
    c = conn.cursor()
    c.execute('SELECT wins, losses FROM user_stats WHERE user_id = ?', (user.id,))
    stats = c.fetchone()
    conn.close()

    if stats:
        wins, losses = stats
        await ctx.send(f'{user.name}, your record: {wins} wins, {losses} losses.')
    else:
        await ctx.send(f'{user.name}, you have no recorded matches yet.')

@bot.command()
async def delete_match(ctx, match_id: int):
    conn = sqlite3.connect('bot_data.db')
    c = conn.cursor()

    try:
        # Check if the match exists
        c.execute('SELECT player1_id, player2_id, winner_id FROM matches WHERE match_id = ?', (match_id,))
        match = c.fetchone()

        if not match:
            await ctx.send(f'Match ID {match_id} not found.')
            return

        player1_id, player2_id, winner_id = match

        # Update user stats
        if winner_id:
            # Deduct a win for the winner
            c.execute('UPDATE user_stats SET wins = wins - 1 WHERE user_id = ?', (winner_id,))

            # Determine the loser and deduct a loss
            loser_id = player1_id if winner_id == player2_id else player2_id
            c.execute('UPDATE user_stats SET losses = losses - 1 WHERE user_id = ?', (loser_id,))
        else:
            # No winner recorded, no stats to adjust
            await ctx.send(f'Match ID {match_id} had no winner, only the match will be deleted.')

        # Delete the match
        c.execute('DELETE FROM matches WHERE match_id = ?', (match_id,))
        conn.commit()
        await ctx.send(f'Match ID {match_id} has been successfully deleted.')

    except sqlite3.Error as e:
        await ctx.send(f"An error occurred while deleting the match: {str(e)}")
    finally:
        conn.close()


@bot.command()
async def alter_winner(ctx, match_id: int, new_winner: discord.Member):
    conn = sqlite3.connect('bot_data.db')
    c = conn.cursor()

    try:
        # Fetch match details
        c.execute('SELECT player1_id, player2_id, winner_id FROM matches WHERE match_id = ?', (match_id,))
        match = c.fetchone()

        if not match:
            await ctx.send(f'Match ID {match_id} not found.')
            return

        player1_id, player2_id, current_winner_id = match

        if new_winner.id not in (player1_id, player2_id):
            await ctx.send(f'{new_winner.name} is not part of Match ID {match_id}.')
            return

        # Determine the new loser
        new_loser_id = player1_id if new_winner.id == player2_id else player2_id

        # Update stats for the current winner (if any)
        if current_winner_id:
            c.execute('UPDATE user_stats SET wins = wins - 1 WHERE user_id = ?', (current_winner_id,))
            current_loser_id = player1_id if current_winner_id == player2_id else player2_id
            c.execute('UPDATE user_stats SET losses = losses - 1 WHERE user_id = ?', (current_loser_id,))

        # Ensure new winner and loser are in user_stats
        c.execute('INSERT OR IGNORE INTO user_stats (user_id, wins, losses) VALUES (?, 0, 0)', (new_winner.id,))
        c.execute('INSERT OR IGNORE INTO user_stats (user_id, wins, losses) VALUES (?, 0, 0)', (new_loser_id,))

        # Update stats for the new winner and loser
        c.execute('UPDATE user_stats SET wins = wins + 1 WHERE user_id = ?', (new_winner.id,))
        c.execute('UPDATE user_stats SET losses = losses + 1 WHERE user_id = ?', (new_loser_id,))

        # Update the match's winner in the database
        c.execute('UPDATE matches SET winner_id = ? WHERE match_id = ?', (new_winner.id, match_id))
        conn.commit()

        await ctx.send(f'Match ID {match_id} has been updated: {new_winner.name} is now the winner.')

    except sqlite3.Error as e:
        await ctx.send(f"An error occurred while updating the match: {str(e)}")

    finally:
        conn.close()


@bot.command()
async def leaderboards(ctx):
    conn = sqlite3.connect('bot_data.db')
    c = conn.cursor()
    c.execute('SELECT user_id, wins, losses FROM user_stats ORDER BY wins DESC')
    leaderboard = c.fetchall()
    conn.close()

    if leaderboard:
        leaderboard_message = "Leaderboard:\n"
        for user_id, wins, losses in leaderboard:
            member = ctx.guild.get_member(user_id)
            if member:
                leaderboard_message += f"{member.name}: {wins} wins, {losses} losses\n"
        await ctx.send(leaderboard_message)
    else:
        await ctx.send('No match records found.')

@bot.command()
async def reset_data(ctx):
    conn = sqlite3.connect('bot_data.db')
    c = conn.cursor()
    c.execute('DELETE FROM matches')
    c.execute('DELETE FROM user_stats')
    c.execute('DELETE FROM sqlite_sequence')

    conn.commit()
    conn.close()
    await ctx.send('All match data and user statistics have been reset.')

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

