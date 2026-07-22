import os
import re
import numpy as np
import pandas as pd

from sentence_transformers import SentenceTransformer
from sklearn.metrics.pairwise import cosine_similarity


# ============================================================
# 1. GET PROJECT DIRECTORY
# ============================================================

BASE_DIR = os.path.dirname(os.path.abspath(__file__))


# ============================================================
# 2. MODEL DIRECTORY
# ============================================================

MODEL_PATH = os.path.join(BASE_DIR,"model","horeca_guardians_model")


# ============================================================
# 3. CSV FILE PATH
# ============================================================

CSV_PATH = os.path.join(MODEL_PATH,"Horeca_Guardians.csv")


# ============================================================
# 4. LOAD SENTENCE TRANSFORMER MODEL
# ============================================================

print("Loading Horeca Guardians model...")

model = SentenceTransformer(MODEL_PATH)

print("Model loaded successfully!")


# ============================================================
# 5. LOAD CSV DATASET
# ============================================================

print("Loading Horeca Guardians CSV...")

df = pd.read_csv(CSV_PATH)


# ============================================================
# 6. CHECK REQUIRED COLUMNS
# ============================================================

required_columns = ["question","answer","category"]


for column in required_columns:

    if column not in df.columns:

        raise ValueError(f"Missing required column: {column}")


print("CSV loaded successfully!")

print("Total questions:",len(df))


# ============================================================
# 7. CLEAN DATA
# ============================================================

# Remove rows where question or answer is empty

df = df.dropna(subset=["question","answer"])


# Convert columns to string

df["question"] = df["question"].astype(str)


df["answer"] = df["answer"].astype(str)


df["category"] = df["category"].fillna("general").astype(str)


# Remove duplicate questions

df = df.drop_duplicates(subset=["question"])


# Reset index

df = df.reset_index(drop=True)


# ============================================================
# 8. TEXT CLEANING FUNCTION
# ============================================================

def clean_text(text):

    text = str(text)

    # Convert to lowercase

    text = text.lower()

    # Remove extra spaces

    text = re.sub(r"\s+"," ",text)

    # Remove spaces at beginning/end

    text = text.strip()

    return text


# ============================================================
# 9. CLEAN QUESTIONS
# ============================================================

df["clean_question"] = df["question"].apply(clean_text)


# ============================================================
# 10. GENERATE QUESTION EMBEDDINGS
# ============================================================

print("Generating question embeddings...")


question_embeddings = model.encode(df["clean_question"].tolist(),convert_to_numpy=True,normalize_embeddings=True,show_progress_bar=True)


print("Question embeddings generated!")


print("Embedding shape:",question_embeddings.shape)


# ============================================================
# 11. SIMILARITY THRESHOLD
# ============================================================

SIMILARITY_THRESHOLD = 0.60


# ============================================================
# 12. CHATBOT RESPONSE FUNCTION
# ============================================================

def get_chatbot_response(user_query):

    # ----------------------------------------
    # Clean user input
    # ----------------------------------------

    cleaned_query = clean_text(user_query)


    # ----------------------------------------
    # Generate embedding for user question
    # ----------------------------------------

    query_embedding = model.encode([cleaned_query],convert_to_numpy=True,normalize_embeddings=True)


    # ----------------------------------------
    # Calculate cosine similarity
    # ----------------------------------------

    similarities = cosine_similarity(query_embedding,question_embeddings)[0]


    # ----------------------------------------
    # Get best matching question
    # ----------------------------------------

    best_index = np.argmax(similarities)


    # ----------------------------------------
    # Get confidence score
    # ----------------------------------------

    best_score = float(
        similarities[best_index])


    # ----------------------------------------
    # Get matching question
    # ----------------------------------------

    matched_question = df.iloc[best_index]["question"]


    # ----------------------------------------
    # Get answer
    # ----------------------------------------

    answer = df.iloc[best_index]["answer"]


    # ----------------------------------------
    # Get category
    # ----------------------------------------

    category = df.iloc[best_index]["category"]


    # ========================================================
    # CHECK CONFIDENCE
    # ========================================================

    if best_score >= SIMILARITY_THRESHOLD:

        return {answer}


    else:

        return {"I'm sorry, I couldn't find "
                "a suitable answer to your question. "
                "Would you like to connect with "
                "a human agent?"}
   
