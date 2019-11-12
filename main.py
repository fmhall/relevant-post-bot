import praw
from dotenv import load_dotenv
import os
import numpy as np

load_dotenv()
client = os.getenv("CLIENT_ID")
secret = os.getenv("CLIENT_SECRET")
username = os.getenv("USERNAME")
password = os.getenv("PASSWORD")

def run():
    reddit = praw.Reddit(user_agent='RelevantChessPostBot',
                         client_id=client, client_secret=secret,
                         username=username, password=password)
    chess = reddit.subreddit('chess')
    anarchychess = reddit.subreddit('anarchychess')
    for ac_post in anarchychess.stream.submissions():
        print("Analyzing post: ", ac_post.title)
        relevant_post, min_distance = get_min_levenshtein(ac_post, chess)
        sim_bool, similarity = is_similar(ac_post, relevant_post, .5)
        if relevant_post and sim_bool:
            max_length = float(max(len(ac_post.title.split()), len(relevant_post.title.split())))
            print(min_distance)
            print(max_length)
            print(similarity)
            certainty = similarity * (1 - (min_distance / max_length))
            print("AC title: ", ac_post.title)
            print("C title: ", relevant_post.title)
            print("Certainty: ", certainty)
            # print("Levenshtein Distance: ", min_distance)
            if certainty > .5:
                try:
                    if username not in [comment.author.name for comment in ac_post.comments]:
                        add_comment(ac_post, relevant_post, certainty)
                    else:
                        print("Already commented")
                except:
                    print("Was rate limited")
                    pass


def add_comment(ac_post, relevant_post, certainty):
    reply_template = "Relevant r/chess post: [{}](https://www.reddit.com{})\n\n".format(relevant_post.title, relevant_post.permalink)
    certainty_tag = "Certainty: {}%\n\n".format(round(certainty*100, 2))
    bot_tag = "^I ^am ^a ^bot ^created ^by ^/u/fmhall, ^inspired ^by [this comment.]({})\n\n".format("https://www.reddit.com/r/AnarchyChess/comments/durvcj/dude_doesnt_play_chess_thinks_he_can_beat_magnus/f78cga9")
    github_tag = "^(I use the Levenshtein distance of both titles to determine relevance. \
                    You can find my source code [here]({}))".format("https://github.com/fmhall/relevant-post-bot")
    comment = reply_template + certainty_tag + bot_tag + github_tag
    ac_post.reply(comment)
    print(comment)
    pass


def get_min_levenshtein(ac_post, chess):
    ac_title = ac_post.title
    min_distance = 100000
    relevant_post = None
    for c_post in chess.hot():
        c_title = c_post.title
        # print(c_title)
        distance = levenshtein(ac_title.split(), c_title.split())
        if distance < min_distance:
            min_distance = distance
            relevant_post = c_post
    return relevant_post, min_distance


def is_similar(ac_post, c_post, factor):
    ac_title_set = set(ac_post.title.split())
    c_title_set = set(c_post.title.split())
    similarity = len(ac_title_set.intersection(c_title_set))
    sim_ratio = similarity / len(ac_title_set)

    if sim_ratio > factor:
        # print("AC title set: ", ac_title_set)
        # print("C title set: ", c_title_set)
        # print("Sim ratio: ", sim_ratio)
        return True, sim_ratio
    return False, 0


def levenshtein(seq1, seq2):
    size_x = len(seq1) + 1
    size_y = len(seq2) + 1
    matrix = np.zeros((size_x, size_y))
    for x in range(size_x):
        matrix[x, 0] = x
    for y in range(size_y):
        matrix[0, y] = y
    for x in range(1, size_x):
        for y in range(1, size_y):
            if seq1[x-1] == seq2[y-1]:
                matrix[x, y] = min(matrix[x-1, y] + 1, matrix[x-1, y-1], matrix[x, y-1] + 1)
            else:
                matrix[x, y] = min(
                    matrix[x-1, y] + 1,
                    matrix[x-1, y-1] + 1,
                    matrix[x, y-1] + 1
                )
    return matrix[size_x - 1, size_y - 1]


run()
