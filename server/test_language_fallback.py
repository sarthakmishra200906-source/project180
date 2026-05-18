from server.core.ai_brain import AIBrain
b = AIBrain()
print('Hindi fallback:')
print(b.respond('Crack a joke in Hindi'))
print('\nHinglish fallback:')
print(b.respond('Crack a joke in Hinglish'))
print('\nEnglish fallback:')
print(b.respond('Crack a joke in English'))
