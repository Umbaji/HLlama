# The system today

HLlama is a WhatsApp assistant for women's sexual and reproductive health, in
Togo and Benin. A person writes to it on WhatsApp; it answers in French.

## The three parts

**The bot** (`bot/`) is what talks to WhatsApp. It holds the flows
(the fact about her health, the nearest health service), the prompt,
and the translation of the answer into the message WhatsApp sends.

**The API** (`backend/`) holds what must outlive a conversation:
the exchanges and what they were about, the consent, the facts a person
declared, and the documentary base the assistant may quote.

**The backoffice** (`admin/`) is where the team reads the service:
the questions asked, the wordings the assistant did not understand, and the
documentary base it draws from.

## How a message travels

1. WhatsApp calls the bot's webhook. The bot checks the signature, then the
   consent: **nothing is answered before the person has agreed**, and the
   agreement is withdrawn when she asks.
2. The scope classifier reads the message. A health question goes to the model
   with the trusted notes: the current time, her preferred name, the facts
   she declared, the passages of the documentary base.
3. A service request never reaches the model as a free question: the model
   copies what she declared, and the code does the rest - it shows a recap,
   and acts only after she confirms.
4. What the model does not know, it does not say. A figure - a dosage, a
   duration - comes from the documentary base, with its source, or it
   is not said.

## What is guaranteed

- **Nothing is invented.** The figures come from the documents, which carry
  their source and their date.
- **Her data is hers.** Her number, her exchanges and the facts she declared
  are encrypted at rest. The analysis of the usage holds aggregates only: a
  theme, a count, an hour. The model never sees a person.
- **A serious situation is answered, not deflected.** The emergency numbers
  come with the offer to find the nearest health service, and with the advice
  to be seen by a professional.
