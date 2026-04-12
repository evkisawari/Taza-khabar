import asyncio
import re
import sys
import os

# Ensure we can import from the current directory
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from sync import summarize

def count_words(text):
    # Support both English and Hindi word counting
    return len(re.findall(r'\S+', text))

async def test_summaries():
    test_cases = [
        {
            "lang": "en",
            "text": "The reserve bank of India has recently announced a new policy regarding the digital currency. This policy aims to regulate the use of cryptocurrency in the country while promoting the use of the digital rupee. The governor stated that this move is essential for the stability of the economy and to prevent money laundering and other financial crimes. Many experts have welcomed this move, saying it will bring clarity to the market. However, some traders are concerned about the impact on their business. The transition is expected to take place over the next several months with multiple phases of implementation. This is a significant step towards a more digital economy. It will help in reducing the costs of cash management and increase financial inclusion across the rural parts of India as well."
        },
        {
            "lang": "hi",
            "text": "भारतीय रिजर्व बैंक ने हाल ही में डिजिटल मुद्रा के संबंध में एक नई नीति की घोषणा की है। इस नीति का उद्देश्य देश में क्रिप्टोकरेंसी के उपयोग को विनियमित करना है और साथ ही डिजिटल रुपये के उपयोग को बढ़ावा देना है। गवर्नर ने कहा कि यह कदम अर्थव्यवस्था की स्थिरता के लिए और मनी लॉन्ड्रिंग और अन्य वित्तीय अपराधों को रोकने के लिए आवश्यक है। कई विशेषज्ञों ने इस कदम का स्वागत किया है, उनका कहना है कि इससे बाजार में स्पष्टता आएगी। हालांकि, कुछ व्यापारी अपने व्यवसाय पर पड़ने वाले प्रभाव को लेकर चिंतित हैं। यह परिवर्तन अगले कई महीनों में कार्यान्वयन के कई चरणों के साथ होने की उम्मीद है। यह डिजिटल अर्थव्यवस्था की ओर एक महत्वपूर्ण कदम है। इससे नकद प्रबंधन की लागत कम करने में मदद मिलेगी और भारत के ग्रामीण हिस्सों में वित्तीय समावेशन बढ़ेगा।"
        }
    ]

    print("Starting Pro Summary Evaluation...")
    print("Range Required: 55-85 words. No '...' allowed.")
    
    for case in test_cases:
        print(f"\n--- Testing Language: {case['lang']} ---")
        summary = await summarize(case['text'], language=case['lang'])
        word_count = count_words(summary)
        
        # Validation
        in_range = 55 <= word_count <= 85
        no_ellipses = not summary.strip().endswith('...')
        clean_end = any(summary.strip().endswith(p) for p in ['.', '।', '!', '|'])
        
        print(f"Summary: {summary}")
        print(f"Word Count: {word_count}")
        
        print(f"Word count check (55-85): {'PASS' if in_range else 'FAIL'}")
        print(f"No ellipses check: {'PASS' if no_ellipses else 'FAIL'}")
        print(f"Clean ending check: {'PASS' if clean_end else 'FAIL'}")

if __name__ == "__main__":
    asyncio.run(test_summaries())
