import json
import math
import os
from datetime import datetime, timedelta, timezone
import subprocess
DATA_FILE = "questions.json"
SCRIPT_FILE = "spaced_repetition.py"
os.chdir(os.path.dirname(os.path.abspath(__file__)))
config = {}
with open('config', 'r') as f:
    for line in f:
        if '=' in line:
            key, value = line.strip().split('=')
            config[key.strip()] = value.strip()

config['COMPANY_PREP_MODE'] = config['COMPANY_PREP_MODE'].lower() == 'true'
config['COMPANY_PREP_RETENTION_FACTOR'] = float(config['COMPANY_PREP_RETENTION_FACTOR'])
request_retention = float(config['DEFAULT_RETENTION'])

def commit(file_name):
    try:
        result = subprocess.run(['git', 'status', '--porcelain'], capture_output=True, text=True)
        if any(line.strip() and not line.startswith('??') for line in result.stdout.splitlines()):
            subprocess.run(['git', 'add', file_name], check=True)
            commit_message = f"updated {file_name}"
            subprocess.run(['git', 'commit', '-m', commit_message], check=True)
            subprocess.run(['git', 'push'], check=True)
            print("Changes committed and pushed.")
    except subprocess.CalledProcessError as e:
        print(f"Error during git operations: {e}")

def load_questions():
    global questions
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r") as f:
            try:
                questions = json.load(f)
                if not questions:
                    questions = {}
            except json.JSONDecodeError:
                questions = {}
    else:
        questions = {}


def save_questions():
    with open(DATA_FILE, "w") as f:
        json.dump(questions, f, indent=4)
    commit(DATA_FILE)

load_questions()

difficulty_order = {
    "Arrays": 1,
    "Hashing": 2,
    "2P": 3,
    "Stack": 4,
    "Sorting": 5,
    "Binary Search": 6,
    "Sliding Window": 7,
    "Linked List": 8,
    "Greedy": 9,
    "Heap": 10,
    "Intervals": 11,
    "Trees": 12,
    "Math": 13,
    "Graphs": 14,
    "Backtracking": 15,
    "Tries": 16,
    "DP": 17
}

interval_cap = 365


class FSRS:
    def __init__(self, w=None):
        # w[8] higher nums slightly speed up interval growth due to limited timeframe
        # ^ if reviews are too frequent for mastered problems, should increase even further
        # w[10] is rejection sensitivity, if not hitting retention goals (forgetting too much, decrease it a bit, otherwise, increase)
        # w[15] is hard penalty, so lower values means stricter sensitivity ratings if rating == 2
        self.w = w if w else (
            2.5, 2.6, 2.3, 2.8, 3.0, 0.8, 0.7, 0.5, 0.1, 0.1, 0.1, 1.0, 0.5, 0.5, 1.0, .6, 1.2, 0.5, 0.7, 1.3)
        self.request_retention = request_retention
        self.maximum_interval = interval_cap
        self.DECAY = -0.4
        self.FACTOR = 0.9 ** (1 / self.DECAY) - 1

    def forgetting_curve(self, elapsed_days, stability):
        return (1 + self.FACTOR * elapsed_days / stability) ** self.DECAY

    def next_interval(self, stability, retention_factor):
        new_interval = stability / self.FACTOR * (retention_factor ** (1 / self.DECAY) - 1)
        return min(max(round(new_interval), 1), self.maximum_interval)

    def next_difficulty(self, difficulty, rating):
        next_d = difficulty - self.w[6] * (rating - 3)
        return min(max(self.mean_reversion(5.0, next_d), 1), 10)

    def next_recall_stability(self, difficulty, stability, retrievability, rating):
        return stability * (
                1
                + math.exp(self.w[8])
                * (11 - difficulty)
                * math.pow(stability, -self.w[9])
                * (math.exp((1 - retrievability) * self.w[10]) - 1)
        ) * (self.w[15] if rating == 2 else 1)

    def mean_reversion(self, init, current):
        return self.w[7] * init + (1 - self.w[7]) * current


fsrs = FSRS()


def add_question(fsrs, question, link, problem_type):
    load_questions()
    problem_type_lower = problem_type.lower()
    difficulty_order_lower = {k.lower(): k for k in difficulty_order.keys()}
    if problem_type_lower not in difficulty_order_lower:
        print(f"Invalid problem type. Please choose from the following: {', '.join(difficulty_order.keys())}")
        return
    problem_type = difficulty_order_lower[problem_type_lower]

    retention_factor = (input("Enter the desired request retention (.8 for normal, .9-.95 for company): ").strip())
    company_tags_input = input("Enter the company tags (separated by commas if multiple): ").strip()
    company_tags = [tag.strip() for tag in company_tags_input.split(',')] if company_tags_input else []

    questions[question] = {
        "link": link,
        "problem_type": problem_type,
        "company_tags": company_tags,
        "last_reviewed": (datetime.now(timezone.utc) + timedelta(hours=-4)).date().isoformat(),
        "next_review": (datetime.now(timezone.utc) + timedelta(hours=-4) + timedelta(days=1)).date().isoformat(),
        "interval": 1,
        "stability": fsrs.w[0],
        "difficulty": 5.0,
        "retention_factor": float(retention_factor) if retention_factor else request_retention,
        "current_retention_rate": None,
        "feynman": "",
        "solving_time": [],
        "average_time": None,
        "ratings": []
    }
    save_questions()
    print(f"Question '{question}' with link '{link}' and type '{problem_type}' added.")


def calculate_average_time(solving_times):
    if solving_times:
        return sum(time['time_taken'] for time in solving_times) / len(solving_times)
    return None

def review_questions(company=None):
    load_questions()
    today = (datetime.now(timezone.utc) + timedelta(hours=-4)).date().isoformat()
    
    filtered_questions = [
        (question, details) for question, details in questions.items()
        if (company is None or company in details.get('company_tags', [])) and
        (details["next_review"] <= today or details["last_reviewed"] == today)
    ]
    
    sorted_questions = sorted(filtered_questions, key=lambda q: difficulty_order[q[1]["problem_type"]])
    unreviewed_questions = [q for q in sorted_questions if q[1]["last_reviewed"] != today]

    if not unreviewed_questions:
        print("No questions to review today.")
        return

    for question, details in sorted_questions:
        checkbox = "[x]" if details["last_reviewed"] == today else "[ ]"
        print(f"{checkbox} {question} ({details['problem_type']})")

    for question, details in unreviewed_questions:
        if not review_single_question(question, details, today):
            continue

    save_questions()



def review_single_question(question, details, today):
    start_problem = input(f'\nReview "{question}" ({details["problem_type"]})? Link: {details["link"]}\n(yes/no): ').strip().lower()
    if 'n' in start_problem:
        print(f"Skipped '{question}'. It remains due for review.")
        return False

    start_time = datetime.now(timezone.utc)
    rating = get_valid_input(f"Rate your recall of '{question}' (1-5): ", lambda x: 1 <= int(x) <= 5)
    questions[question]["ratings"].append({"date": today, "rating": rating})
    questions[question]["current_retention_rate"] = sum(5 if rating["rating"] >= 4 else rating["rating"] for rating in questions[question]["ratings"] if rating['rating']) / (len(questions[question]["ratings"]) * 5)    
    difference_in_retention = abs(questions[question]["current_retention_rate"] - questions[question]["retention_factor"]) * 100
    if questions[question]["current_retention_rate"] > questions[question]["retention_factor"]:
        print(f"You're hitting your retention goal! You're up by {difference_in_retention:.2f}%!")
    else:
        print(f"You're not hitting your retention goal. You're down by {difference_in_retention:.2f}%!")

    time_taken = (datetime.now(timezone.utc) - start_time).total_seconds() / 60
    questions[question]["solving_time"].append({"date": today, "time_taken": time_taken})
    questions[question]["average_time"] = calculate_average_time(questions[question]["solving_time"])

    update_question_metrics(question, rating)

    explanation = input(f"Explain the solution to '{question}' as if teaching someone else: ").strip()
    questions[question]["feynman"] = explanation
    questions[question]["last_reviewed"] = today

    return True

def update_question_metrics(question, rating):
    details = questions[question]
    last_interval = details["interval"]
    last_stability = details["stability"]
    last_difficulty = details["difficulty"]
    retention_factor = details["retention_factor"]
    if config['COMPANY_PREP_MODE'] and config['COMPANY_PREP_TARGET'] not in details.get('company_tags', []):
        retention_factor *= config.COMPANY_PREP_RETENTION_FACTOR
    
    retrievability = fsrs.forgetting_curve(last_interval, last_stability)
    new_stability = fsrs.next_recall_stability(last_difficulty, last_stability, retrievability, rating)
    new_difficulty = fsrs.next_difficulty(last_difficulty, rating)
    base_interval = fsrs.next_interval(new_stability, retention_factor)

    if rating == 1:
        base_interval = 1
        new_stability = max(new_stability * 0.6, 0.1)

    new_interval = min(base_interval, interval_cap)
    next_review = ((datetime.now(timezone.utc) + timedelta(hours=-4) + timedelta(days=new_interval))).date().isoformat()

    details.update({
        "interval": new_interval,
        "stability": new_stability,
        "difficulty": new_difficulty,
        "next_review": next_review
    })

    print(f"Old Stability: {last_stability:.2f}")
    print(f"New Stability: {new_stability:.2f}")
    print(f"Old Difficulty: {last_difficulty:.2f}")
    print(f"New Difficulty: {new_difficulty:.2f}")
    print(f"Next review date: {next_review}")



def get_valid_input(prompt, validator):
    while True:
        try:
            user_input = input(prompt)
            if validator(user_input):
                return int(user_input)
        except ValueError:
            pass
        print("Invalid input. Please try again.")


def list_all_questions():
    load_questions()
    if not questions:
        print("No questions added yet.")
        return
    grouped_questions = {}
    for question, details in questions.items():
        problem_type = details["problem_type"]
        if problem_type not in grouped_questions:
            grouped_questions[problem_type] = []
        grouped_questions[problem_type].append((question, details))

    sorted_problem_types = sorted(grouped_questions.keys(), key=lambda pt: difficulty_order[pt])

    print("All questions (sorted by difficulty):")
    for problem_type in sorted_problem_types:
        print(f"\n{problem_type}:")
        for question, details in grouped_questions[problem_type]:
            print(f" - {question}")
            for key, value in details.items():
                print(f"     {key.replace('_', ' ').title()}: {value}")
            print("")
    print(f"Total number of question: {len(questions)}")

def main():
    while True:
        print("\nSpaced Repetition System")
        print("1. Review Questions")
        print("2. Add New Question")
        print("3. List All Questions")
        print("4. Review Questions by Company")
        print("5. Exit and Commit")
        print("6. Toggle Company Prep Mode")
        print("7. View Statistics")
        choice = get_valid_input("Choose an option: ", lambda x: x in "1234567")
        
        if choice == 1:
            review_questions()
        elif choice == 2:
            add_new_question()
        elif choice == 3:
            list_all_questions()
        elif choice == 4:
            company = input("Enter the company to review: ").strip()
            review_questions(company)
        elif choice == 5:
            print("Goodbye!")
            commit(SCRIPT_FILE)
            commit(DATA_FILE)
            commit('config')
            break
        elif choice == 6:
            toggle_company_prep_mode()
        elif choice == 7:
            view_statistics()
def add_new_question():
    question = input("Enter the question name: ")
    link = input("Enter the NeetCode/LeetCode link: ")
    print("Problem types:", ", ".join(difficulty_order.keys()))
    problem_type = input("Enter the problem type: ")
    add_question(fsrs, question, link, problem_type)
def toggle_company_prep_mode():
    config['COMPANY_PREP_MODE'] = not config['COMPANY_PREP_MODE']
    if config['COMPANY_PREP_MODE']:
        config['COMPANY_PREP_TARGET'] = input("Enter the target company for prep mode: ").strip()
        print(f"Company Prep Mode activated for {config['COMPANY_PREP_TARGET']}")
    else:
        config['COMPANY_PREP_TARGET'] = ""
        print("Company Prep Mode deactivated")
    
    with open('config', 'w') as f:
        for key, value in config.items():
            f.write(f"{key} = {value}\n")
def view_statistics():
    load_questions()
    total_retention_rate = sum(details['current_retention_rate'] for details in questions.values() if details['current_retention_rate']) / sum(1 for details in questions.values() if details['current_retention_rate'])
    print(f"Total Retention Rate: {total_retention_rate}")
    print("Request Retention Rate: ", request_retention)
    print("Difference in retention rate: ", total_retention_rate - request_retention)

if __name__ == "__main__":
    main() 