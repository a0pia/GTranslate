from deep_translator import GoogleTranslator

class Translator:
    def __init__(self, target_lang='tr'):
        self.target_lang = target_lang
        self.translator = GoogleTranslator(source='auto', target=target_lang)

    def change_target_language(self, target_lang):
        """Updates the target language for the translator."""
        self.target_lang = target_lang
        self.translator = GoogleTranslator(source='auto', target=target_lang)

    def translate(self, text):
        """
        Translates text to the target language.
        """
        if not text.strip():
            return ""
        
        try:
            translation = self.translator.translate(text)
            return translation
        except Exception as e:
            print(f"Translation Error: {e}")
            return f"Error: {e}"

if __name__ == "__main__":
    t = Translator()
    print(t.translate("Hello world, this is a test."))
