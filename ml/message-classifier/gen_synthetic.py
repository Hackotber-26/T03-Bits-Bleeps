"""
Generate a large synthetic message dataset with an "Unclassified" category.

Contents: category templates x slot fillers (banks, brands, amounts, links,
names, dates...) + decorative noise. Seeded -> reproducible.

Input : classified_messages.csv (optional, only used for template reference)
Output: classified_messages_synthetic.csv   (synthetic rows only)
        classified_messages_augmented.csv   (original rows + synthetic rows)
"""
import csv
import random
from datetime import datetime, timedelta
from pathlib import Path

random.seed(42)
ROOT = Path(__file__).parent
OUT_SYN = ROOT / "classified_messages_synthetic.csv"
OUT_AUG = ROOT / "classified_messages_augmented.csv"

PER_CLASS = 700  # rows per category

# ------------------------------------------------------------------ fillers
BANKS = ["IDFC FIRST Bank", "HDFC Bank", "ICICI Bank", "Axis Bank", "SBI",
         "Kotak Bank", "Paytm Payments Bank", "Airtel Payments Bank",
         "Yes Bank", "IndusInd Bank", "Federal Bank", "Central Bank of India", "Canara Bank"]
BRANDS = ["Zomato", "Swiggy", "Flipkart", "Amazon", "Ajio", "Myntra",
          "BigBasket", "Zepto", "Swiggy Instamart", "PharmEasy", "1mg",
          "Rapido", "Uber", "Ola", "Naturals Salon", "Urban Company", "SonyLIV"]
SCAM_BRANDS = ["HDFC KYC Cell", "RBI Wallet Division", "Axis Reward Desk",
               "SBI Outcome Team", "CoinSecure Trading", "Xpress Loan Bazaar",
               "Vruchi Finance Point", "Green Power Trade Desk", "Quick Value Alerts",
               "PayPoint Gift Zone"]
NAMES = ["Ananya", "Rahul", "Meera", "Arjun", "Taniqa", "Arnab", "Kabir",
         "Divya", "Musavir", "Neha", "Farhan", "Harshit", "Shruti", "Imran", "Priya"]
UID_CHARS = "abcdefghijklmnopqrstuvwxyz0123456789"


def rid(n=8):
    return "".join(random.choice(UID_CHARS) for _ in range(n))


def link(host=True):
    slug = rid(random.choice([5, 6, 7, 8]))
    dom = random.choice(["nextbanking.com/sms-helpdesk", "upivery.xyz/claim-now",
                         "urgent-kyc.click/card-update", "reward-point.live/gift",
                         "tinytrack.me/parcel", "securepay-access.co/verify"])
    return ("http://" if random.random() < 0.7 else "https://") + dom + "/" + slug


def amt():
    return random.choice(
        [x for x in range(10, 5000, 5)] + random.choices([i * 1000 for i in range(1, 30)], k=20))


def acct():
    return f"XXXXXX{random.randint(100000, 999999)}"


def ref():
    return str(random.randint(10**8, 10**12))


def when():
    d = datetime(2025, 1, 1) + timedelta(days=random.randint(0, 700),
                                         minutes=random.randint(0, 1439))
    return d.strftime("%d/%m/%y %H:%M"), d.strftime("%Y-%m-%d") + \
        f" {d.strftime('%H:%M:%S')}"


def otp():
    return "".join(random.choice("0123456789") for _ in range(random.choice([4, 6])))


def phone_no():
    return f"+91-{random.randint(7000000000, 9989999999)}"


def sender(category):
    if category == "Safe - Transactional":
        body = f"{''.join(w[0].upper() for w in random.choice(BANKS + BRANDS).split())[:4]}"
        return f"{random.choice(['AX', 'VM', 'JD', 'TD', 'AD', 'BX'])}-{body}-S"
    if category == "Promotional":
        body = f"{''.join(w[0].upper() for w in random.choice(BRANDS + ['MyAirtel', 'RushShop']).split())[:4]}"
        return f"{random.choice(['AX', 'VM', 'JD', 'TD'])}-{body}-S"
    if category in ("Unsafe / Suspicious", "Spam"):
        return random.choice([phone_no(), f"RCS-{random.randint(1000, 9999)}", "+1-442239880"])
    return random.choice(NAMES + [phone_no(), ""])


# ------------------------------------------------------------------ templates
def t_personal():
    topics = ["the match", "the movie", "the exam", "the trip", "the pizza", "the song",
              "the assignment", "the series", "the meeting", "the playlist"]
    t = [
        "Hey {n}, are we still meeting at {h} o'clock tmrw?",
        "{n}, I'll call you back later.",
        "Thanks a lot {n}! Really appreciate it!",
        "Did you watch the match last night {n}?",
        "Please text me when you reach home {n}.",
        "Sending u the list in a sec {n}",
        "I'm sick {n}, can we reschedule checkout to Sunday?",
        "Ok {n} sounds good",
        "{n}: lunch tmrw? I found this cute cafe.",
        "So proud of you {n}!! wait till you see the pics",
        "Where are you {n}? I've been waiting for 20 min",
        "Happy birthday {n}!!! have the best year ahead",
        "{n} I left the keys under the mat",
        "Do you have my charger {n}? Also I took your notes for reference",
        "Everytime I hear this song I remember our trip {n}",
        "Hi",
        "Tmkoc",
        "Yes that works for me",
        "Nothing much, just waiting for the weekend {n}",
        "{n} the movie was actually good, watched till 3am",
        "It's raining here {n}, don't forget your umbrella",
        "Okkk {n} I'll ask aunty",
        "{n} can you believe these prices? anyway see you tomorrow",
        "Bro what a plot twist in {topic} {n}",
        "did you finish {topic} yet?",
        "went way overboard with {topic} honestly",
        "Nah skip {topic}, it's not worth the hype {n}",
        "{n} thanks for lending me notes for {topic}",
        "Marmalade toast and {topic} kind of morning {n}",
        "Please remind me about {topic} at {h}",
        "how was {topic}?? spill {n}",
        "We can discuss {topic} later tonight {n}",
        "No way!!! {topic} was actually amazing {n}",
        "one more episode of {topic} and I swear I'll sleep {n}",
    ]
    return random.choice(t).format(n=random.choice(NAMES), h=random.randint(5, 9),
                                   topic=random.choice(topics))


def t_transactional():
    tmpl = random.choice([
        "Dear Customer, your a/c {ac} is debited by Rs.{a} on {d} for purchase at {b}. Not you? call 18001234 now. {bank}",
        "Your A/C {ac} is credited with INR {a} on {d}. New Bal :INR {bal}. {bank}",
        "Rs {a} debited from a/c XX{ac} towards Electricity bill payment. Avl Bal Rs {bal}. {bank}",
        "{a} spent on card xx{ac} at {b} on {d}. Avl Bal Rs {bal}. {bank}",
        "Your UPI transaction of Rs {a} on {d} to {b} has FAILED / refunded. {bank}",
        "Auto-renewal notice: your {b} plan (Rs {a}) renews on {d}. To manage, visit Play Store subscriptions. {bank}",
        "Dear customer, GST refund of Rs {a} has been credited to your acct XX{ac}. {bank}",
        "{otp} is your OTP to login to your {bank} account. Do not share with anyone.",
        "Rs.{a} debited from a/c xx{ac} on {d}. Net payable remains Rs {bal}. Team {bank}",
        "Your order from {b} was delivered on {d}. Something wrong? call {phone}. {bank}",
        "Electricity board: Bill of Rs {a} due on {d} for acct {ac}. {bank}",
    ])
    return tmpl.format(
        ac=acct(), a=amt(), b=random.choice(BRANDS + ["Croma Retail", "Reliance Digital"]),
        bal=f"{amt():,}", d=when()[0], bank=random.choice(BANKS),
        otp=otp(), phone=random.randint(18000100, 18009999), ref=ref(),
    )


def t_promotional():
    tmpl = random.choice([
        "Dear Customer, Thanks for your interest in {b}. Click link to start: {l}",
        "Hi {n}, special offer from {b}! Get {off}% OFF on {cat} today only: {l}",
        "Hello {n}, Rs.{a} bonus cashback is waiting inside your {b} app. Tap now {l}",
        "{b}: activating your FIRSTmoney-style Smart Personal Loan offer of Rs.{a}. Apply instantly {l}",
        "{b} Maha Sale is LIVE! {cat} from Rs.99 + extra 10% with code {c}. Shop {l}",
        "Final reminder {n}, your {b} Gold trial ends {d}. Renew Rs.{a}& keep benefits: {l}",
        "Refer {n} on {b}, you both earn Rs.{a}. Invite now {l}",
        "{b} exclusive {cat} deal unlocked for premium users like you. Grab it {l}",
        "Weekend flash: flat {off}% off {cat}. Only on {b}. Code {c}. T&C apply {l}",
    ])
    return tmpl.format(
        b=random.choice(BRANDS), a=amt(), off=random.choice([10, 20, 25, 40, 50, 60, 70]),
        cat=random.choice(["fashion", "groceries", "electronics", "grooming", " prescription pickups",
                           "kitchen goods", "fitness gear", "toys"]),
        d=random.choice(["tomorrow", "tonight", "Sunday", "31st Dec"]),
        c=f"{random.choice(['SAVE', 'FLAT', 'BIG'])}{random.randint(10, 99)}",
        l=link(), n=random.choice(NAMES), ref=ref(), phone=random.randint(18100100, 18109999),
    )


def t_unsafe():
    tmpl = random.choice([
        "Dear user, your KYC expires {d}. Update at {l} otherwise account blocked {b}",
        "Dear Customer, kit account overdue, click {l} to verify your cards.",
        "Dear user, You've won the {b} contest! Prize Rs.{a}. To claim register: {l}",
        "Your account was generated without Odds. Last date {d}. Click {l} to activate.",
        "Paytm wallet par balance timed out. KYC karne ke liye {l} kholo urgently.",
        "Dear user, your {b} account will be blocked in 24 hours. Update PAN & Aadhaar: {l} (Terms)",
        "You have been selected for work-from-home session with {b}: Rs.{a}/daily, signup {l}",
        "Final notice: pay EMI Rs {a} for loan XXXX{r} today via {l} to avoid legal action. {b}",
        "Your {b} card is deactivated due to suspicious usage. Verify NOW: {l}",
        "Reward of Rs {a} pending on {b}. Claim your Amazon voucher http://vouchers-claim.xyz/{r} within 1 day.",
        "Government is giving free laptop & Rs.{a}, all students eligible. Apply {l} — last date {d}.",
        "Cash available instantly at rupees {a} on your {b} account. Use credit line now: {l} T&C",
        "Dear user, our {b} agents already noticed unusual activity from your location. report here {l}",
        "Hi, I'm stuck in Dublin wallet. Send me Rs {a} on this UPI ID urgently, I'll return it. Its me {n}",
    ])
    return tmpl.format(
        a=amt(), d=random.choice(["today", "tomorrow", "31/12", "12th Jan", "24 hrs"]),
        l=link(host=False), r=rid(4), b=random.choice(SCAM_BRANDS + ["RBI", "Paytm", "your bank"]),
        ref=ref(), id=ref(), n=random.choice(NAMES), ref2=ref(),
    )


def t_spam():
    placeholders = ["[application/vnd.gsma.botmessage.v1.0+json]", "[image/png]",
                    "[image/jpeg]", "[video/mp4]", "[image/gif]", "[audio/ogg]",
                    "[application/pdf]", "[contact/vcard]", "[location]"]
    junk = [
        "WINNER WINNER!!! your mobile number won 25 LAKH lottery, send details to claim",
        "You have 1 new secure voicemail, missed call alert from +0{r}",
        "Cheap online pharmacy! best prices, no prescription needed, order now",
        "Earn $500/day from home, no investment, limited seats, join group now",
        "Best untimely HOT deals in your town, teens love it, tap to watch",
        "Free recharge of Rs{a} for first 100 users, forward this to 10 friends",
        "Greetings, your subscription has been auto enhanced for VIP tier {r}",
        "Casino royale biggest jackpot is waiting for you, play and win daily",
        "Your parcel #{a} could not be delivered last week, re-schedule here",
        "This is not a marketing SMS. This is not a marketing SMS. This is not.",
    ]
    if random.random() < 0.75:
        return " ".join(random.sample(placeholders, random.randint(2, 4)))
    return random.choice(junk).format(a=amt(), r=rid(6))


MMS_NOTE = "[application/vnd.gsma.botmessage.v1.0+json] [image/png]"


def t_unclassified():
    tmpl = random.choice([
        "reminder: pick up {cat} from the shop",
        "My number is {p}, stored for reference only.",
        "meeting-{r} joined you in room 4",
        "WIFI pass is {c}",
        "window warning: Low storage on device",
        "{n} visitle {l}",
        "Signal lost for device",
        "The 4th point on slide {r} is actually wrong {n}",
        "its called shr纳ruz i think",
        "ok",
        "hmm",
        "{n} what did I do with that parcel",
        "playlist song second: 4 remix",
        "If the shoe fits wear it I guess",
        "kaise ho {n}?",
        "note to self: chest + surds + extra bedsheet",
        "wifi का password बता देना",
        "Student-ID: STU{r}",

        "Unlock code {c} for the gate",
        "Where's that PDF you sent last week?",
        "System update available, install it tonight only {n}",
        "I won't be able to attend the {cat} meeting today {n}.",
        "Your app #{r} was restarted properly for connection",
        "Bet u'll never guess what I found in that old trunk",
        "Actually wait nevermind {n}",
        "This song is stuck in my head since morning",
        "Let's sit near the window in the class tmrw {n}",
        "ok bye someone's at the door",
        "Aaj zyada garmi hai",
        "bag space low: delete some files from {cat}",
        "accesscard expiring: renew till {d}",
        "Turn left after the temple, then straight for 2 km {n}",
        "Pls remember to lock the {cat} when you leave",
        "Somebody parked scooter right outside the {cat} again",
        "bday list: {n}, {n}, {n} (in order)",
        " Avg 32, count 18, last error 0.02 -- debug log line",
        "previously deleted messages recovered. {r}",
        "Keep the leftovers on the second shelf, else rot",
        "I think this font looks better than the other one",
        "यह message read करके delete कर देना",
        "stuck tyre happened on {d}",
        "Devon khabar nahi, {n} tu hi bol de",
        "the charger has a dent but works fine",
        "That quiz app is rigged I swear",
        "Add {n} to the group so we can finalise venue",
        "Do NOT reply to that number again {n}",
        "game lagging too much today",
    ])
    return tmpl.format(
        n=random.choice(NAMES + ["buddy", "guys", ""] ), cat=random.choice(
            ["grocery", "pharmacy", "notary", "kids school", "green", "car", "garbage", "uniform"]),
        r=random.randint(10, 9999), c=rid(random.choice([4, 6, 8])).upper(),
        p=phone_no(), d=random.choice(["4 Aug", "Monday", "tomorrow", "20/11"]),
        ref=ref(), ref2=ref(), l=link(host=False),
    )


GEN = {"Safe - Personal": t_personal,
       "Safe - Transactional": t_transactional,
       "Promotional": t_promotional,
       "Unsafe / Suspicious": t_unsafe,
       "Spam": t_spam,
       "Unclassified": t_unclassified}

REASON = {
    "Safe - Personal": "Saved contact / human conversation",
    "Safe - Transactional": "Account / OTP / order / service notification from a known sender",
    "Promotional": "Marketing/offer message from a recognised brand",
    "Unsafe / Suspicious": "Phishing / prize-bait / credential-harvesting wording",
    "Spam": "Junk MMS/bot payload",
    "Unclassified": "Message content that does not fit any known category",
}


def rows_for(cat):
    gen, out, fails = GEN[cat], [], 0
    while len(out) < PER_CLASS:
        content = gen()
        if content in seen:
            fails += 1
            if fails > 500:  # accept duplicates rather than loop forever
                break
            continue  # dedupe synthetic rows
        fails = 0
        seen.add(content)
        ts, dt = when()
        out.append({
            "DateTime": f"{dt} 06:42:37",
            "Direction": "Received" if random.random() < 0.9 else "Sent",
            "Contact": random.choice(NAMES) if cat == "Safe - Personal" else
            ("" if cat == "Spam" and random.random() < 0.5 else sender(cat)),
            "Phone": random.choice([phone_no(), ""]),
            "Content": content,
            "Type": "SMS" if cat != "Spam" and random.random() > 0.2 else "MMS",
            "Category": cat,
            "Reason": REASON[cat],
            "SourceFile": "synthetic_generator",
        })
    return out


seen = set()
synthetic = []
for cat in GEN:
    synthetic.extend(rows_for(cat))

random.shuffle(synthetic)

with open(OUT_SYN, "w", encoding="utf-8", newline="") as f:
    w = csv.DictWriter(f, fieldnames=["DateTime", "Direction", "Contact", "Phone",
                                      "Content", "Type", "Category", "Reason", "SourceFile"])
    w.writeheader()
    w.writerows(synthetic)

# augmented = original + synthetic
orig = list(csv.DictReader(open(ROOT / "classified_messages.csv", encoding="utf-8-sig")))
with open(OUT_AUG, "w", encoding="utf-8", newline="") as f:
    w = csv.DictWriter(f, fieldnames=list(orig[0].keys()))
    w.writeheader()
    w.writerows(orig + [{k: r[k] for k in w.fieldnames} for r in synthetic])

print(f"synthetic rows: {len(synthetic)} -> {OUT_SYN.name}")
print(f"augmented rows: {len(orig) + len(synthetic)} -> {OUT_AUG.name}")
