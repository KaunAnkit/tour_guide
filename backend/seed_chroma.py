"""
seed_chroma.py
--------------
Populate the ChromaDB vector store with B.R. Ambedkar biography excerpts,
famous speeches, photo metadata, and article references.

Run once:  python seed_chroma.py
"""

import chromadb, os, pathlib

DB_PATH = str(pathlib.Path(__file__).parent / "chroma_db")

client = chromadb.PersistentClient(path=DB_PATH)
collection = client.get_or_create_collection(
    name="ambedkar_museum",
    metadata={"hnsw:space": "cosine"},
)

# ── Documents to seed ──────────────────────────────────────────────
documents = [
    # --- Biography ---
    {
        "id": "bio-01",
        "text": (
            "Bhimrao Ramji Ambedkar was born on 14 April 1891 in Mhow, "
            "Central Provinces (now Madhya Pradesh). He was the 14th and last "
            "child of Ramji Maloji Sakpal and Bhimabai. The family belonged to "
            "the Mahar caste, classified as 'untouchable' under the Hindu "
            "caste system. Despite extreme discrimination, young Bhimrao "
            "excelled in school."
        ),
        "metadata": {"type": "biography", "topic": "early life"},
    },
    {
        "id": "bio-02",
        "text": (
            "Ambedkar earned a scholarship from the Maharaja of Baroda and "
            "sailed to the United States in 1913. He studied at Columbia "
            "University, earning an MA (1915) and a PhD (1927) in Economics. "
            "His doctoral thesis examined the evolution of provincial finance "
            "in British India. He later studied at the London School of "
            "Economics and was admitted to the bar at Gray's Inn, London."
        ),
        "metadata": {"type": "biography", "topic": "education"},
    },
    {
        "id": "bio-03",
        "text": (
            "After returning to India, Ambedkar launched a lifelong fight "
            "against caste discrimination. He organised the Mahad Satyagraha "
            "in 1927, leading thousands of Dalits to drink water from the "
            "public Chavadar Tank, asserting their equal right to public "
            "resources. He also burned copies of the Manusmriti as a symbolic "
            "rejection of caste-based laws."
        ),
        "metadata": {"type": "biography", "topic": "social reform"},
    },
    {
        "id": "bio-04",
        "text": (
            "In 1935 Ambedkar declared he would not die a Hindu. After two "
            "decades of study, he publicly converted to Navayana Buddhism on "
            "14 October 1956 at Deekshabhoomi, Nagpur, along with nearly "
            "600,000 followers—the largest mass religious conversion in "
            "recorded history."
        ),
        "metadata": {"type": "biography", "topic": "buddhism conversion"},
    },
    {
        "id": "bio-05",
        "text": (
            "As chairman of the Drafting Committee, B.R. Ambedkar is hailed "
            "as the chief architect of the Constitution of India, adopted on "
            "26 November 1949. He championed fundamental rights, abolished "
            "untouchability under Article 17, and ensured reservations for "
            "Scheduled Castes and Scheduled Tribes. He served as Independent "
            "India's first Law Minister from 1947 to 1951."
        ),
        "metadata": {"type": "biography", "topic": "constitution"},
    },
    {
        "id": "bio-06",
        "text": (
            "Ambedkar's economic vision emphasised state industrialisation, "
            "agrarian reform, and the abolition of the Khoti system. He played "
            "a key role in establishing the Reserve Bank of India, drawing on "
            "his 1923 paper 'The Problem of the Rupee'. He also championed "
            "labour rights, introducing the 8-hour workday to India."
        ),
        "metadata": {"type": "biography", "topic": "economics"},
    },
    {
        "id": "bio-07",
        "text": (
            "Ambedkar passed away on 6 December 1956 at his home in Delhi. "
            "He was posthumously awarded the Bharat Ratna, India's highest "
            "civilian honour, in 1990. His legacy endures through Ambedkar "
            "Jayanti (14 April), a national public holiday, and through the "
            "countless institutions, universities, and memorials named after "
            "him across India."
        ),
        "metadata": {"type": "biography", "topic": "legacy"},
    },

    # --- Speeches ---
    {
        "id": "speech-01",
        "text": (
            "Speech at the Round Table Conference, London, 1930–1932: "
            "'What is the village but a sink of localism, a den of ignorance, "
            "narrow-mindedness and communalism?' Ambedkar argued for separate "
            "electorates for the Depressed Classes, clashing with Gandhi."
        ),
        "metadata": {"type": "speech", "topic": "round table conference"},
    },
    {
        "id": "speech-02",
        "text": (
            "'Annihilation of Caste' (1936) — an undelivered address that "
            "became one of the most important anti-caste texts ever written. "
            "Ambedkar argued that caste is not merely a division of labour "
            "but a division of labourers, and that inter-dining and "
            "inter-marriage alone cannot destroy it. He called for a "
            "'revolution in values'."
        ),
        "metadata": {"type": "speech", "topic": "annihilation of caste"},
    },
    {
        "id": "speech-03",
        "text": (
            "Constituent Assembly Speech, 25 November 1949: 'On the 26th of "
            "January 1950, we are going to enter into a life of "
            "contradictions. In politics we will have equality and in social "
            "and economic life we will have inequality… We must remove this "
            "contradiction at the earliest possible moment, or else those who "
            "suffer from inequality will blow up the structure of political "
            "democracy.' This speech remains one of the most quoted addresses "
            "in Indian parliamentary history."
        ),
        "metadata": {"type": "speech", "topic": "constituent assembly"},
    },
    {
        "id": "speech-04",
        "text": (
            "'Who Were the Shudras?' (1946) and 'The Untouchables' (1948) "
            "are major scholarly works where Ambedkar examined the historical "
            "origins of caste. He argued the Shudras were originally Kshatriyas "
            "degraded by Brahmin priests, and that untouchability arose from "
            "the stigma attached to beef-eating broken men."
        ),
        "metadata": {"type": "speech", "topic": "scholarly works"},
    },
    {
        "id": "speech-05",
        "text": (
            "'Buddha or Karl Marx' (1956) — Ambedkar's philosophical essay "
            "comparing Buddhism and Marxism. He concluded that while both "
            "sought to end suffering and exploitation, Buddhism achieved this "
            "through moral transformation without violence, making it the "
            "superior path for social revolution."
        ),
        "metadata": {"type": "speech", "topic": "buddha or karl marx"},
    },

    # --- Photo/exhibit metadata ---
    {
        "id": "photo-01",
        "text": (
            "Photograph: Young Bhimrao at age 10, taken in Satara circa 1901. "
            "Shows him in formal attire, reflecting his family's military "
            "background — his father Ramji Sakpal served in the British Indian "
            "Army."
        ),
        "metadata": {
            "type": "photo",
            "topic": "childhood",
            "image_url": "/static/exhibits/young_ambedkar.jpg",
        },
    },
    {
        "id": "photo-02",
        "text": (
            "Photograph: Ambedkar at Columbia University, New York, circa 1914. "
            "He is seen in Western academic attire. He studied under John Dewey "
            "and Edwin Seligman, whose ideas on pragmatism and public finance "
            "profoundly shaped his thinking."
        ),
        "metadata": {
            "type": "photo",
            "topic": "columbia university",
            "image_url": "/static/exhibits/columbia_ambedkar.jpg",
        },
    },
    {
        "id": "photo-03",
        "text": (
            "Photograph: The Mahad Satyagraha, March 1927. A large crowd of "
            "Dalit activists marches toward the Chavadar Tank. This was the "
            "first major act of civil disobedience by the Dalit community for "
            "equal access to public water sources."
        ),
        "metadata": {
            "type": "photo",
            "topic": "mahad satyagraha",
            "image_url": "/static/exhibits/mahad_satyagraha.jpg",
        },
    },
    {
        "id": "photo-04",
        "text": (
            "Photograph: Ambedkar signing the Constitution of India as Chairman "
            "of the Drafting Committee, 1949. The Constitution, the longest "
            "written constitution of any country, enshrines fundamental rights "
            "and the abolition of untouchability."
        ),
        "metadata": {
            "type": "photo",
            "topic": "constitution signing",
            "image_url": "/static/exhibits/constitution_signing.jpg",
        },
    },
    {
        "id": "photo-05",
        "text": (
            "Photograph: Mass conversion ceremony at Deekshabhoomi, Nagpur, "
            "14 October 1956. Ambedkar and approximately 600,000 followers "
            "converted to Buddhism. The site is now a major Buddhist pilgrimage "
            "destination."
        ),
        "metadata": {
            "type": "photo",
            "topic": "deekshabhoomi conversion",
            "image_url": "/static/exhibits/deekshabhoomi.jpg",
        },
    },

    # --- Articles / reference metadata ---
    {
        "id": "article-01",
        "text": (
            "Article: 'Castes in India: Their Mechanism, Genesis and "
            "Development' — a paper read before Prof. A.A. Goldenweiser's "
            "Anthropology seminar at Columbia University on 9 May 1916. "
            "Ambedkar argued endogamy is the essence of caste."
        ),
        "metadata": {
            "type": "article",
            "topic": "castes in india",
            "url": "https://www.columbia.edu/itc/mealac/pritchett/00ambedkar/txt_ambedkar_castes.html",
        },
    },
    {
        "id": "article-02",
        "text": (
            "Article: 'The Problem of the Rupee: Its Origin and Its Solution' "
            "(1923) — Ambedkar's DSc thesis at the London School of Economics. "
            "This work influenced the formation of the Reserve Bank of India."
        ),
        "metadata": {
            "type": "article",
            "topic": "problem of the rupee",
            "url": "https://en.wikipedia.org/wiki/The_Problem_of_the_Rupee",
        },
    },
    {
        "id": "article-03",
        "text": (
            "Article: 'States and Minorities' (1947) — a memorandum submitted "
            "to the Constituent Assembly proposing state socialism, "
            "nationalisation of key industries, and collective farming. "
            "Ambedkar considered economic democracy essential to political "
            "democracy."
        ),
        "metadata": {
            "type": "article",
            "topic": "states and minorities",
            "url": "https://www.mea.gov.in/ambedkar.html",
        },
    },
]

# ── Upsert into ChromaDB ───────────────────────────────────────────
ids = [d["id"] for d in documents]
texts = [d["text"] for d in documents]
metadatas = [d["metadata"] for d in documents]

collection.upsert(ids=ids, documents=texts, metadatas=metadatas)
print(f"✓  Seeded {len(ids)} documents into '{collection.name}' at {DB_PATH}")
