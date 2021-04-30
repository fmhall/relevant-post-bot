import os
from typing import Tuple
from praw import Reddit
from praw.models import Submission
from praw.models import Subreddit
from dotenv import load_dotenv
import numpy as np
import pickledb
from typing import Iterator, Callable
import threading
import logging
import string
import time

# I've saved my API token information to a .env file, which gets loaded here
load_dotenv()
CLIENT = os.getenv("CLIENT_ID")
SECRET = os.getenv("CLIENT_SECRET")
USERNAME = os.getenv("USERNAME")
PASSWORD = os.getenv("PASSWORD")

# Set the path absolute path of the chess_post database
pickle_path = os.path.dirname(os.path.abspath(__file__)) + "/chess_posts.db"
db = pickledb.load(pickle_path, True)

# Create the reddit object instance using Praw
reddit = Reddit(
    user_agent="RelevantChessPostBot",
    client_id=CLIENT,
    client_secret=SECRET,
    username=USERNAME,
    password=PASSWORD,
)
# Constants
CERTAINTY_THRESHOLD = 0.50
SIMILARITY_THRESHOLD = 0.40

GITHUB_TAG = (
    "[^(fmhall)](https://www.reddit.com/user/fmhall) ^| [^(github)]({})\n".format(
        "https://github.com/fmhall/relevant-post-bot"
    )
)
log_format = "%(asctime)s: %(threadName)s: %(message)s"
logging.basicConfig(format=log_format, level=logging.INFO, datefmt="%H:%M:%S")
logger = logging.getLogger(__name__)


def restart(handler: Callable):
    """
    Decorator that restarts threads if they fail
    """

    def wrapped_handler(*args, **kwargs):
        logger.info("Starting thread with: %s", args)
        while True:
            try:
                handler(*args, **kwargs)
            except Exception as e:
                logger.error("Exception: %s", e)

    return wrapped_handler


@restart
def run(
    circlejerk_sub_name: str = "anarchychess",
    original_sub_name: str = "chess",
    quiet_mode: bool = False,
    add_os_comment: bool = True,
    certainty_threshold: float = CERTAINTY_THRESHOLD,
    similarity_threshold: float = SIMILARITY_THRESHOLD,
):
    """
    The main loop of the program, called by the thread handler
    """
    # Instantiate the subreddit instances
    original_sub: Subreddit = reddit.subreddit(original_sub_name)
    circlejerk_sub: Subreddit = reddit.subreddit(circlejerk_sub_name)
    parody_count = 0
    # This loops forever, streaming submissions in real time from the circlejerk sub as they get posted
    for cj_post in circlejerk_sub.stream.submissions():
        logger.info(f"Analyzing post: {cj_post.title}")

        # Gets the original sub post in hot with the minimum levenshtein distance
        relevant_post, min_distance = get_min_levenshtein(cj_post, original_sub)

        # Are the post's words similar and to what degree?
        sim_bool, similarity = is_similar(cj_post, relevant_post, similarity_threshold)

        if relevant_post and sim_bool:
            max_length = float(
                max(len(cj_post.title.split()), len(relevant_post.title.split()))
            )

            # Certainty is calculated with this arbitrary formula that seems to work well
            certainty = 1 - (min_distance / max_length)
            old_certainty = similarity * 1 - (min_distance / max_length)
            # Continue to next post if crosspost
            if (
                is_crosspost(cj_post, relevant_post)
                or cj_post.author == relevant_post.author
            ):
                continue

            # Log useful stats
            logger.info(
                f"Minimum distance: {min_distance}",
            )
            logger.info(
                f"Maximum length: {max_length}",
            )
            logger.info(
                f"Similarity: {similarity}",
            )
            logger.info(f"CJ title: {cj_post.title}")
            logger.info(f"RP title: {relevant_post.title}")
            logger.info(f"Certainty: {certainty}")
            logger.info(f"Old Certainty: {old_certainty}")

            if max_length <= 3:
                certainty = old_certainty
            if certainty > certainty_threshold:
                parody_count += 1
                logger.info(f"Parody count: {parody_count}")
            if certainty > CERTAINTY_THRESHOLD and not quiet_mode:
                try:
                    authors = []
                    if cj_post.comments:
                        for comment in cj_post.comments:
                            if comment.author:
                                authors.append(comment.author.name)
                    if USERNAME in authors:
                        logger.info("Already commented on CJ post")
                    else:
                        add_circlejerk_comment(cj_post, relevant_post, certainty)

                except Exception as error:
                    logger.error(f"Was rate limited: {error}")
                    pass
                if add_os_comment:
                    # update the original subs post's comment with the relevant CJ posts
                    try:
                        add_original_sub_comment(relevant_post, cj_post)

                    except Exception as error:
                        logger.error(f"Was rate limited: {error}")


def add_circlejerk_comment(
    cj_post: Submission, relevant_post: Submission, certainty: float
) -> None:
    """
    Adds a comment to the circlejerk_sub post. If anyone knows how to format it so my username is also superscripted,
    please submit a PR.

    :param cj_post: circlejerk_sub post
    :param relevant_post: original_sub post
    :param certainty: Certainty metric
    :return: None
    """
    nsfw_tag = ""
    if relevant_post.over_18:
        nsfw_tag = "[NSFW] "
    reply_template = "Relevant r/{} post: [{}{}](https://www.reddit.com{})\n\n".format(
        relevant_post.subreddit.display_name,
        nsfw_tag,
        relevant_post.title,
        relevant_post.permalink,
    )
    certainty_tag = "Certainty: {}%\n\n".format(round(certainty * 100, 2))
    comment = reply_template + certainty_tag + GITHUB_TAG
    cj_post.reply(comment)
    logger.debug(comment)
    logger.info(f"Added comment to {cj_post.subreddit.display_name}")


def add_original_sub_comment(relevant_post: Submission, cj_post: Submission) -> None:
    """
    Adds a comment to the original_sub post.

    :param relevant_post: original_sub post
    :param cj_post: circlejerk_sub post
    :return: None
    """
    rpid = str(relevant_post.id)
    cjpid = str(cj_post.id)
    if not db.get(rpid):
        db.set(rpid, [cjpid])
    else:
        rid_list = db.get(rpid)
        rid_list = list(set(rid_list))
        if cjpid not in rid_list:
            rid_list.append(cjpid)
        db.set(rpid, rid_list)
    posts = [reddit.submission(id=p) for p in db.get(rpid)]
    posts.sort(key=lambda x: x.score, reverse=True)
    post_tags = []
    for post in posts:
        if post and post.author:
            nsfw_tag = ""
            if post.over_18:
                nsfw_tag = "[NSFW] "
            post_tags.append(
                "[{}{}](https://www.reddit.com{}) by {}\n\n".format(
                    nsfw_tag, post.title, post.permalink, post.author
                )
            )
    posts_string = "".join(post_tags)
    reply_template = (
        "This post has been parodied on r/{0}.\n\n"
        "Relevant r/{0} posts: \n\n{1}".format(
            cj_post.subreddit.display_name, posts_string
        )
    )

    comment_string = reply_template + GITHUB_TAG
    authors = []
    if relevant_post.comments:
        for comment in relevant_post.comments:
            if comment.author:
                authors.append(comment.author.name)
    if USERNAME not in authors and len(post_tags) > 0:
        relevant_post.reply(comment_string)
        logger.debug(comment_string)
        logger.info(f"Added comment to {relevant_post.subreddit.display_name}")
    else:
        for comment in relevant_post.comments:
            if comment.author:
                if comment.author.name == USERNAME:
                    logger.debug(comment.body)
                    if comment_string != comment.body:
                        if len(post_tags) > 0:
                            comment.edit(comment_string)
                            logger.info("edited")
                        else:
                            comment.delete()
                            logger.info("Comment deleted")
                    else:
                        logger.info("Comment is the same as last time, not editing")


def get_min_levenshtein(
    cj_post: Submission, original_sub: Subreddit
) -> (Submission, float):
    """
    This function iterates through the hot posts in the original_sub subreddit and finds the one with the smallest levenshtein
    distance to the circlejerk_sub post.
    :param cj_post: circlejerk_sub post
    :param original_sub: original_sub subreddit
    :return: tuple with the original sub's post with the smallest LD, and the distance
    """
    cj_title = standardize_title(cj_post.title)
    min_distance = 100000
    relevant_post = None
    for os_post in original_sub.hot():
        os_title = standardize_title(os_post.title)
        distance = levenshtein(cj_title.split(), os_title.split())
        if distance < min_distance:
            min_distance = distance
            relevant_post = os_post
    return relevant_post, min_distance


def is_similar(
    cj_post: Submission, os_post: Submission, factor: float
) -> Tuple[bool, float]:
    """

    :param cj_post: circlejerk_sub post
    :param os_post: original_sub post
    :param factor: float indicating smallest proportion of similar words
    :return: boolean indicating if the proportion is similar and the proportion of words the posts
    share divided by the length of the longer post
    """
    cj_title = standardize_title(cj_post.title)
    os_title = standardize_title(os_post.title)
    cj_title_set = set(cj_title.split())
    os_title_set = set(os_title.split())
    similarity = len(cj_title_set.intersection(os_title_set))
    sim_ratio = similarity / max(len(cj_title_set), len(os_title_set))

    if sim_ratio > factor:
        return True, sim_ratio

    return False, 0.0


def levenshtein(seq1: list, seq2: list) -> float:
    """
    The Levenshtein distance is a string metric for measuring the difference between two sequences. Informally,
    the Levenshtein distance between two words is the minimum number of single-character edits (i.e. insertions,
    deletions, or substitutions) required to change one word into the other. While it is normally used to compare
    characters in a sequence, if you treat each word in a sentence like a character, then it can be used on sentences.
    :param seq1: First sentence
    :param seq2: Second sentence
    :return: The levenshtein distance between the two
    """
    size_x = len(seq1) + 1
    size_y = len(seq2) + 1
    matrix = np.zeros((size_x, size_y))
    for x in range(size_x):
        matrix[x, 0] = x
    for y in range(size_y):
        matrix[0, y] = y
    for x in range(1, size_x):
        for y in range(1, size_y):
            if seq1[x - 1] == seq2[y - 1]:
                matrix[x, y] = min(
                    matrix[x - 1, y] + 1, matrix[x - 1, y - 1], matrix[x, y - 1] + 1
                )
            else:
                matrix[x, y] = min(
                    matrix[x - 1, y] + 1, matrix[x - 1, y - 1] + 1, matrix[x, y - 1] + 1
                )
    return float(matrix[size_x - 1, size_y - 1])


def is_crosspost(cj_post: Submission, relevant_post: Submission) -> bool:
    duplicates: Iterator[Submission] = cj_post.duplicates()
    for duplicate in duplicates:
        if duplicate.id == relevant_post.id:
            logger.info("Post is a cross-post, not commenting")
            return True
    return False


def standardize_title(title: str) -> str:
    title = title.lower().translate(str.maketrans("", "", string.punctuation))
    return title


@restart
def delete_bad_comments(username: str):
    """
    Delete bad comments, called by the thread handler
    """
    # Instantiate the subreddit instances
    comments = reddit.redditor(username).comments.new(limit=100)

    for comment in comments:
        logger.debug(f"Analyzing {comment.body}")
        should_delete = comment.score < 0
        if should_delete:
            logger.info(f"Deleting comment {str(comment.body)}")
            comment.delete()
        else:
            logger.debug("Not deleting")
    time.sleep(60 * 15)


if __name__ == "__main__":
    logger.info("Main    : Creating threads")
    threads = []
    chess_thread = threading.Thread(target=run, args=(), name="chess")
    tame_impala_thread = threading.Thread(
        target=run,
        args=(
            "tameimpalacirclejerk",
            "tameimpala",
        ),
        name="tame_impala",
    )
    flying_thread = threading.Thread(
        target=run, args=("shittyaskflying", "flying"), name="flying"
    )
    aviation_thread = threading.Thread(
        target=run, args=("shittyaskflying", "aviation", False, False), name="aviation"
    )
    fly_fishing_thread = threading.Thread(
        target=run, args=("flyfishingcirclejerk", "flyfishing"), name="fly_fishing"
    )
    cricket_thread = threading.Thread(
        target=run, args=("CricketShitpost", "Cricket"), name="cricket"
    )
    soccer_thread = threading.Thread(
        target=run, args=("soccercirclejerk", "soccer"), name="soccer"
    )
    chessbeginners_thread = threading.Thread(
        target=run, args=("anarchychess", "chessbeginners"), name="chessbeginners"
    )
    mapporn_thread = threading.Thread(
        target=run, args=("mapporncirclejerk", "mapporn"), name="mapporn"
    )
    cleanup_thread = threading.Thread(
        target=delete_bad_comments, args=[USERNAME], name="cleanup"
    )

    threads.append(chess_thread)
    threads.append(tame_impala_thread)
    threads.append(flying_thread)
    threads.append(aviation_thread)
    threads.append(fly_fishing_thread)
    threads.append(cricket_thread)
    threads.append(soccer_thread)
    threads.append(chessbeginners_thread)
    threads.append(mapporn_thread)
    threads.append(cleanup_thread)

    logger.info("Main    : Starting threads")
    for thread in threads:
        thread.start()
