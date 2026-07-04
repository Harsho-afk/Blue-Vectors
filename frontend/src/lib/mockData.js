// Mock profile generator — used as fallback when the backend is unreachable.

const SUBS = [
  "programming", "technology", "MachineLearning",
  "Python", "webdev", "datascience", "cscareerquestions",
];

const REDDIT_SAMPLES = [
  "Just published a write-up on using graph neural networks for cross-platform identity resolution. Would love feedback from anyone working in OSINT or social network analysis.",
  "Anyone else find that stylometric features are more stable across platforms than username similarity? Testing this hypothesis now.",
  "Hot take: most identity resolution papers ignore the temporal dimension entirely. Posting cadence tells you more than vocabulary.",
  "Finally got PRAW auto-throttling working correctly. The key is not fighting it — just let it sleep when it needs to.",
  "Built a small CLI tool for bulk Reddit profile collection. Runs at ~3 users/minute without hitting rate limits.",
  "Question: is it ethical to build identity linkage systems for research purposes if the data is fully public?",
  "The PAN 2020 dataset is surprisingly underutilized for authorship verification tasks. Highly recommend it.",
  "Comparing BERT-tiny vs LSTM for stylometric feature extraction. BERT wins on accuracy, LSTM wins on inference speed.",
  "Posted in r/MachineLearning but it got buried — has anyone tried combining SHAP with GNN node embeddings for explainability?",
  "Good paper: 'StyleLink: Cross-Platform Identity Resolution via Stylometric Graph Alignment' (ICWSM 2025). Closest prior work to what we're building.",
];

const TWITTER_SAMPLES = [
  "Working on a new approach to cross-platform identity resolution — combining stylometry + GNN + SHAP. Thread incoming.",
  "Fascinating how much temporal patterns reveal about authorship. People are creatures of habit, even online.",
  "New paper dropped on authorship verification. Reading it now — the contrastive loss approach is interesting.",
  "Hot take: username similarity is the weakest signal for identity linkage. Change my mind.",
  "Just open-sourced our ARIA data collection layer. Reddit + Twitter, fully async, PostgreSQL backed.",
  "The OSINT community needs better tooling for ethical research. Building something about this.",
  "Running ablation experiments on our fusion model. Graph features matter more than expected.",
  "Anyone else using twikit for Twitter data collection? Curious about stability at scale.",
  "SHAP values for identity resolution explainability — actually pretty readable output. Investigators seem to like it.",
  "Hackathon deadline in 3 weeks. The grind is real. Also the GNN training on Colab keeps timing out.",
];

export function generateMockProfile(platform, username, limit) {
  const now = Date.now() / 1000;
  const samples = platform === "reddit" ? REDDIT_SAMPLES : TWITTER_SAMPLES;
  const posts = [];

  for (let i = 0; i < Math.min(limit, samples.length * 2); i++) {
    const isComment = platform === "reddit" && i % 3 === 2;
    const sub = SUBS[Math.floor(Math.random() * SUBS.length)];
    posts.push({
      text: samples[i % samples.length],
      timestamp: now - i * 3600 * (6 + Math.random() * 18),
      metadata: platform === "reddit"
        ? { type: isComment ? "comment" : "submission", subreddit: sub, score: Math.floor(Math.random() * 400) + 1 }
        : { type: "tweet", tweet_id: String(1800000000000000000n + BigInt(i)), retweet_count: Math.floor(Math.random() * 40), favorite_count: Math.floor(Math.random() * 200), reply_count: Math.floor(Math.random() * 20), lang: "en" },
    });
  }

  posts.sort((a, b) => b.timestamp - a.timestamp);
  const usedSubs = [...new Set(posts.filter(p => p.metadata?.subreddit).map(p => p.metadata.subreddit))];

  return {
    platform,
    username,
    display_name: username.charAt(0).toUpperCase() + username.slice(1),
    bio: platform === "reddit"
      ? "Researcher @ PES University. Building ARIA — cross-platform identity resolution. ML + graphs + XAI."
      : "SOCMINT researcher. Building tools for ethical identity resolution. GNN + stylometry + SHAP.",
    location: platform === "twitter" ? "Bangalore, India" : "",
    profile_image_url: "",
    created_utc: now - 365 * 24 * 3600 * (2 + Math.random() * 4),
    posts,
    subreddits: platform === "reddit" ? usedSubs.sort() : [],
    karma:          platform === "reddit"  ? Math.floor(Math.random() * 8000) + 500 : null,
    follower_count: platform === "twitter" ? Math.floor(Math.random() * 2000) + 100 : null,
    following_count:platform === "twitter" ? Math.floor(Math.random() * 800)  + 50  : null,
  };
}
