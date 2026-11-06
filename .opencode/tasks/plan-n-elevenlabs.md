# Phase N: an ElevenLabs voice can be bought

## Objective

A story film whose narrator is an ElevenLabs voice can estimate, authorize, buy
and recover its takes through the same journal as a MiniMax voice. Today the
voices are listed when a key exists and a quote refuses them: "elevenlabs
voices can't be bought yet; choose a Runware voice".

## What the code and the provider showed, 6 Nov 2026

- `voices.py` has one `Voice` interface; `ElevenLabsVoice.build_request` and
  `parse_result` exist and were proved only against a fake. `narration.py`
  quotes, buys, finishes and recovers through `RunwareClient` alone: a Runware
  schema is read at quote time and re-checked at generate time, a result is
  `{taskUUID, audioURL, cost}`, and a take is recovered by its task UUID.
- The owner's key is `ELEVENLABS_API_KEY` in `~/.secrets.zsh`, which the shell
  exports and `config.effective_settings` reads. The catalogue lists the
  account's voices under that key, with their free previews.
- ElevenLabs, read from its reference today: `POST
  /v1/text-to-speech/{voice_id}/with-timestamps` with header `xi-api-key`
  answers JSON `{audio_base64, alignment{characters,
  character_start_times_seconds, character_end_times_seconds}}`; the format is
  the `output_format` query (default `mp3_44100_128`; 44.1 kHz WAV needs Pro).
  No response header reports a cost, and no task id is returned. `GET
  /v1/user/subscription` reports `character_count`, `character_limit`,
  `next_character_count_reset_unix`, `can_extend_character_limit` and
  `current_overage`, no price per character. `GET /v1/history` lists
  generations with `history_item_id`, `text`, `voice_id`, `model_id`,
  `date_unix`; `GET /v1/history/{id}/audio` downloads one. The API price page
  lists $0.08 per 1,000 characters for `eleven_multilingual_v2` and `eleven_v3`
  and $0.04 for `eleven_flash_v2_5`; what a plan charges past its allowance is
  not stated there.

## Decisions

- D1. One path. An ElevenLabs voice goes through `narration.quote_lines`,
  `generate`, `finish_take` and `recover_take` unchanged in shape: the client
  is chosen by the voice's provider and answers the same four verbs as the
  fake (`schema`, `submit_speech`, `recover_speech`, `download_audio`).
- D2. Money is honest about its basis. The provider reports no dollars, so a
  take's reserve and its cost are its characters times the catalogue price of
  the model, and the task says `cost_basis: "catalogue price, read <date>"`.
  The subscription's `character_count` before and after the call is recorded
  on the task as what the provider counted. The journal stays strict: the cost
  is written once, before the audio is written, and never changed.
- D3. The terms stand in for the schema. At quote time the subscription view
  and the catalogue price row are written under `work/schemas/` and hashed
  into the quote; generate refuses a quote whose terms changed. A quote that
  needs more characters than the period has left is refused by number unless
  the account can extend its limit, in which case the quote says so.
- D4. Recovery reads the history. With no task id at the provider, an
  interrupted take is looked for among the account's generations after the
  task's submission with the same text, voice and model, and its audio is
  downloaded from the history. Nothing is resubmitted; none found leaves the
  task for the owner to reconcile, as today.
- D5. The model is a setting. `voices.elevenlabs_model` (default
  `eleven_multilingual_v2`) names the model every ElevenLabs voice speaks with;
  the catalogue lists the three priced models. The Voices tab offers the choice
  when the provider is ElevenLabs and says the price.
- D6. The audio is kept as received, MP3 at 44.1 kHz 128 kbps, the format every
  tier allows; takes already accept MP3. The provider's character times are
  kept on the take as words, which the free align step may use or replace.

## Tasks

- N1. The catalogue's three ElevenLabs speech models with prices and the read
  date; `Voices.elevenlabs_model`; the Voices tab's model choice.
- N2. `providers.ElevenLabsClient`: terms, submit, recover through the history,
  download; proved against an `httpx.MockTransport`.
- N3. `narration.py` chooses the client by the voice's provider; the quote,
  the take and the recovery for an ElevenLabs voice, proved against a fake.
- N4. The record.

## Not changing

The Runware path and its reserve. The settings schema version. Dialogue,
voice cloning, and the align step. No live call in tests, and none in this
phase without the owner's authorization.

## Acceptance

A film whose narrator is an ElevenLabs voice quotes with the catalogue price
and the account's remaining characters, journals a take with its basis and
the provider's count, stores the MP3 and its words, and recovers an
interrupted take from the history. A Runware voice behaves exactly as before.
Every suite green.

## Done, 6 Nov 2026

### Proved

- `tests/test_providers.py`: the client asks `/v1/text-to-speech/{voice}/with-timestamps`
  as JSON with `xi-api-key` and `output_format=mp3_44100_128`, holds the decoded
  MP3 until the journal asks, reports the provider's character count as the
  subscription's difference, refuses a non-audio answer and never echoes a
  refusal's text; an interrupted take is found in the history by words, voice,
  model and time and its audio downloaded from there; an existing file is never
  overwritten.
- `tests/test_narration.py`: an ElevenLabs quote carries the period and the
  catalogue price under `work/schemas`, reserves at that rate, says how many
  characters the period has left, refuses by number past it unless the plan
  extends, and refuses an unpriced model; a take is journaled at the rate with
  `cost_basis: "catalogue price, read 2026-11-06"` and the provider's count,
  kept as MP3 with its words; an interrupted take is recovered from the history
  and never bought twice. A MiniMax voice's tests pass unchanged.
- The owner's key, read from the environment, passed the provider's free test
  call and listed the account's ten voices into the catalogue; the Voices tab
  offers them with the model choice and its price. Every suite green; the
  committed frontend build is current.

### Not proven

- A live take. No paid call was made; the first ElevenLabs take, a few cents,
  needs the owner's authorization in the Studio, and its character count and
  the plan's charge are what the journal will then show.
