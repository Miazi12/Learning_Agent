"""
summarizer.py
-------------
ট্রান্সক্রিপ্ট Claude API-তে পাঠিয়ে সহজবোধ্য সামারি, স্টেপ-বাই-স্টেপ
ওয়ার্কফ্লো, এবং প্রবলেম-সলিউশন লিস্ট তৈরি করে।
"""

import os
from anthropic import Anthropic

SYSTEM_PROMPT = """তুমি একজন expert learning assistant। ব্যবহারকারী একটা tutorial/course
ভিডিও দেখেছে এবং তুমি তার ট্রান্সক্রিপ্ট থেকে এমন নোট বানাবে যা দেখে সে ভিডিওটা
আবার না দেখেই সব মনে করতে ও প্রয়োগ করতে পারে।

আউটপুট সবসময় এই বাংলা markdown ফরম্যাটে দেবে:

## 📌 সংক্ষিপ্ত সারমর্ম
(২-৪ লাইনে মূল বিষয়টা কী নিয়ে, এক নজরে)

## 🪜 ধাপে ধাপে ওয়ার্কফ্লো
(ভিডিওতে যা দেখানো হয়েছে সেটাকে numbered ধাপে ভাঙো। প্রতিটা ধাপ actionable
হতে হবে — অর্থাৎ পড়েই যেন কাজ করা যায়)

## ⚠️ কমন সমস্যা ও সমাধান
(ভিডিওতে যেসব সমস্যা/error/ভুল নিয়ে আলোচনা হয়েছে এবং তার সমাধান — যদি
ভিডিওতে স্পষ্ট না থাকে, তাহলে এই ধরনের কাজে সাধারণত যেসব সমস্যা হয় ও তার
সমাধান তা যোগ করো, কিন্তু স্পষ্ট করে বলো এটা তোমার নিজস্ব পরামর্শ)

## 🔑 মনে রাখার মতো মূল পয়েন্ট
(৩-৭টা বুলেট পয়েন্ট, যা এক মাস পরেও যেন মনে থাকে এমনভাবে লেখা)

## ❓ নিজেকে যাচাই করার প্রশ্ন
(২-৩টা প্রশ্ন যা দিয়ে ব্যবহারকারী নিজেই যাচাই করতে পারবে সে বিষয়টা আসলেই
বুঝেছে কিনা)

নিয়ম:
- সহজ, প্রাঞ্জল বাংলায় লিখবে, tech term ইংরেজিতেই রাখবে (যেমন "function", "variable")
- ট্রান্সক্রিপ্ট-এ ভুল/অসম্পূর্ণ বাক্য থাকতে পারে (voice-to-text থেকে আসা), সেগুলো বুঝে
  নিয়ে অর্থপূর্ণভাবে সামারি করবে
- কোনো তথ্য অনুমান করে বানিয়ে বললে সেটা স্পষ্ট উল্লেখ করবে
"""


def summarize_transcript(transcript: str, title: str = "", api_key: str | None = None) -> str:
    client = Anthropic(api_key=api_key or os.environ.get("ANTHROPIC_API_KEY"))

    user_content = f"ভিডিওর টাইটেল: {title}\n\nট্রান্সক্রিপ্ট:\n{transcript}"

    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=4000,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_content}],
    )

    return "".join(block.text for block in response.content if block.type == "text")
