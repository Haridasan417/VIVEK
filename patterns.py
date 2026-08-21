"""Scam-pattern similarity store.

Implements the architecture's "shared scam-pattern database + vector similarity
search" using TF-IDF + cosine similarity (scikit-learn) rather than a dedicated
vector DB (Pinecone/Weaviate/pgvector). This is a deliberate scope decision:

- TF-IDF needs no model download, no GPU, and rebuilds in milliseconds — it will
  actually run reliably on a Render free-tier dyno with cold starts.
- A sentence-embedding model (e.g. sentence-transformers) would be more semantically
  accurate but adds ~100-400MB of model weights and slower cold starts. Swap it in
  later (Phase 2+) once you're deploying somewhere with persistent compute — the
  PatternStore interface below (match/add) stays the same either way.

Patterns are seeded from real, publicly documented Indian scam categories
(digital arrest, UPI collect-request/refund, fake KYC, loan-app harassment,
fake job offers, romance/matrimonial scams, courier-customs scam, OTP phishing).
"""
from dataclasses import dataclass

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity


@dataclass
class Pattern:
    pattern_id: str
    name: str
    category: str
    sample_texts: list[str]


@dataclass
class PatternMatch:
    pattern_id: str
    name: str
    category: str
    similarity: float


SEED_PATTERNS: list[Pattern] = [
    Pattern(
        pattern_id="digital_arrest",
        name="Digital Arrest / Fake Law Enforcement Call",
        category="impersonation",
        sample_texts=[
            "This is CBI officer speaking your Aadhaar is linked to a parcel containing drugs you are under digital arrest",
            "Police case has been filed against you, stay on video call or you will be arrested immediately",
            "Your bank account is linked to money laundering, cooperate with income tax officer or face arrest warrant",
            "Customs has seized your parcel containing illegal items, this is a police verification call do not disconnect",
        ],
    ),
    Pattern(
        pattern_id="upi_collect_refund",
        name="UPI Collect Request / Fake Refund",
        category="financial",
        sample_texts=[
            "I sent you money by mistake please accept the collect request to refund it",
            "Your cashback of 500 rupees is ready, approve the UPI request to receive the amount",
            "Scan this QR code to receive your refund from the online seller",
            "Approve the payment request on PhonePe GPay to get your prize money credited",
        ],
    ),
    Pattern(
        pattern_id="fake_kyc",
        name="Fake KYC Update / Account Suspension",
        category="financial",
        sample_texts=[
            "Your bank account will be suspended today complete your KYC immediately by clicking this link",
            "Dear customer your SIM card will be deactivated update your KYC now to avoid disconnection",
            "Your PAN card is not linked update KYC within 24 hours or account will be blocked",
        ],
    ),
    Pattern(
        pattern_id="loan_app_harassment",
        name="Loan App Harassment / Recovery Threats",
        category="harassment",
        sample_texts=[
            "You have not repaid the loan we will inform all your contacts and share your photo",
            "Pay the pending amount now or we will send recovery agents to your home and office",
            "We have accessed your contact list, repay immediately or face public humiliation",
        ],
    ),
    Pattern(
        pattern_id="fake_job_offer",
        name="Fake Job Offer / Part-time Task Scam",
        category="employment",
        sample_texts=[
            "Congratulations you are selected for a work from home job paying 5000 rupees per day just like and subscribe videos",
            "Join our telegram channel to start earning daily by completing simple tasks, pay registration fee first",
            "HR is offering you a part time job, complete the tasks and pay a small deposit to unlock withdrawal",
        ],
    ),
    Pattern(
        pattern_id="romance_matrimonial",
        name="Romance / Matrimonial Scam",
        category="social_engineering",
        sample_texts=[
            "I love you and want to marry you but I am stuck at customs please send money for my release",
            "My gift is stuck at the airport please pay the customs duty so I can send it to you",
            "I am an army officer posted abroad I need money urgently for my return ticket to meet you",
        ],
    ),
    Pattern(
        pattern_id="courier_customs",
        name="Courier / Customs Parcel Scam",
        category="impersonation",
        sample_texts=[
            "Your parcel from FedEx is held at customs containing illegal substances press 1 to speak to an officer",
            "A courier in your name has been seized by customs department, pay the fine to release it",
        ],
    ),
    Pattern(
        pattern_id="otp_phishing",
        name="OTP Phishing",
        category="credential_theft",
        sample_texts=[
            "Please share the OTP sent to your number to verify your identity and complete the process",
            "For refund processing kindly tell me the six digit code you just received",
        ],
    ),
]


class PatternStore:
    def __init__(self, patterns: list[Pattern] | None = None) -> None:
        self._patterns: list[Pattern] = list(patterns or SEED_PATTERNS)
        self._vectorizer: TfidfVectorizer | None = None
        self._matrix = None
        self._flat_index: list[tuple[int, str]] = []  # (pattern_index, sample_text)
        self._rebuild()

    def _rebuild(self) -> None:
        self._flat_index = [
            (p_idx, sample)
            for p_idx, pattern in enumerate(self._patterns)
            for sample in pattern.sample_texts
        ]
        if not self._flat_index:
            self._vectorizer = None
            self._matrix = None
            return
        corpus = [sample for _, sample in self._flat_index]
        self._vectorizer = TfidfVectorizer(stop_words="english", ngram_range=(1, 2))
        self._matrix = self._vectorizer.fit_transform(corpus)

    def add_confirmed_sample(self, pattern_id: str, sample_text: str) -> bool:
        """Feedback loop hook: call this when a human confirms a real scam text
        matching (or extending) a known pattern. Rebuilds the TF-IDF index so the
        next /analyze call benefits immediately — this is the 'shared database
        that keeps learning' from the architecture doc, made concrete."""
        for pattern in self._patterns:
            if pattern.pattern_id == pattern_id:
                pattern.sample_texts.append(sample_text)
                self._rebuild()
                return True
        return False

    def list_patterns(self) -> list[dict]:
        return [
            {"pattern_id": p.pattern_id, "name": p.name, "category": p.category, "sample_count": len(p.sample_texts)}
            for p in self._patterns
        ]

    def match(self, text: str, threshold: float = 0.35) -> PatternMatch | None:
        if not text or self._vectorizer is None or self._matrix is None:
            return None
        query_vec = self._vectorizer.transform([text])
        similarities = cosine_similarity(query_vec, self._matrix)[0]
        best_idx = similarities.argmax()
        best_score = float(similarities[best_idx])
        if best_score < threshold:
            return None
        pattern_idx, _sample = self._flat_index[best_idx]
        pattern = self._patterns[pattern_idx]
        return PatternMatch(
            pattern_id=pattern.pattern_id,
            name=pattern.name,
            category=pattern.category,
            similarity=round(best_score, 3),
        )


pattern_store = PatternStore()
