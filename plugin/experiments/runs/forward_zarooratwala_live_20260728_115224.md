# Run log — `wa-forward-live-1785219745`

- JSONL: `plugin/experiments/runs/forward_zarooratwala_live_20260728_115224.jsonl`
- Events: 2530

| seq | status | kind | detail |
|----:|:------:|------|--------|
| 1 | ok | whatsapp_forward_message | find the zarooratwala link sent to kulvinder on whatsapp and forward to pallavi |
| 2 | ok | step | checking Terminal Accessibility |
| 3 | ok | check | pass |
| 4 | ok | check | pass |
| 5 | fail | check | fail |
| 6 | ok | check | pass |
| 7 | ok | step | launched via open -a |
| 8 | ok | step | WhatsApp startup settle |
| 9 | ok | step | app=WhatsApp screenshot=True |
| 10 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 11 | ok | step | sources=['pyobjc_ax', 'macapptree'] agreement=0.7 |
| 12 | ok | observation |  |
| 13 | ok | world_patch | call |
| 14 | ok | step | dismissing dialogs=['14/146'] |
| 15 | ok | step | after preclear dialog |
| 16 | ok | step | app=WhatsApp screenshot=True |
| 17 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 18 | ok | step | sources=['pyobjc_ax', 'macapptree'] agreement=0.7 |
| 19 | ok | observation |  |
| 20 | ok | world_patch | dialog |
| 21 | ok | step | attempt 1: leaving open='WhatsApp for Mac' toward chat list |
| 22 | ok | step | after preclear list |
| 23 | ok | step | app=WhatsApp screenshot=True |
| 24 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 25 | ok | step | sources=['pyobjc_ax', 'macapptree'] agreement=0.7 |
| 26 | ok | observation |  |
| 27 | ok | world_patch | dialog |
| 28 | ok | step | attempt 2: leaving open='dialog close button' toward chat list |
| 29 | ok | step | after preclear list |
| 30 | ok | step | app=WhatsApp screenshot=True |
| 31 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 32 | ok | step | sources=['pyobjc_ax', 'macapptree'] agreement=0.7 |
| 33 | ok | observation |  |
| 34 | ok | world_patch | dialog |
| 35 | ok | step | closed-loop goal=find the zarooratwala link sent to kulvinder on whatsapp and forward to pallavi |
| 36 | ok | loop_budget |  |
| 37 | ok | step | app=WhatsApp screenshot=True |
| 38 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 39 | ok | step | sources=['pyobjc_ax', 'macapptree'] agreement=0.7 |
| 40 | ok | observation |  |
| 41 | ok | observation |  |
| 42 | ok | storage_cleanup |  |
| 43 | ok | step | storage pressure cleanup |
| 44 | ok | step | app=WhatsApp screenshot=True |
| 45 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 46 | ok | step | sources=['pyobjc_ax', 'macapptree'] agreement=0.7 |
| 47 | ok | observation |  |
| 48 | ok | observation |  |
| 49 | ok | forward_task |  |
| 50 | ok | world_patch | dialog |
| 51 | ok | goal_status |  |
| 52 | ok | decision_engine |  |
| 53 | ok | planner_decision |  |
| 54 | ok | execution | pressed Escape |
| 55 | ok | step | transition settle |
| 56 | ok | step | app=WhatsApp screenshot=True |
| 57 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 58 | ok | step | sources=['pyobjc_ax', 'macapptree'] agreement=0.7 |
| 59 | ok | observation |  |
| 60 | ok | step | transition poll |
| 61 | ok | step | app=WhatsApp screenshot=True |
| 62 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 63 | ok | step | sources=['pyobjc_ax', 'macapptree'] agreement=0.7 |
| 64 | ok | observation |  |
| 65 | ok | step | transition poll |
| 66 | ok | perception_retry |  |
| 67 | ok | step | perception retry (fusion_agreement_low) |
| 68 | ok | step | app=WhatsApp screenshot=True |
| 69 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 70 | ok | step | sources=['pyobjc_ax', 'macapptree'] agreement=0.7 |
| 71 | ok | observation |  |
| 72 | fail | perception_unsettled |  |
| 73 | ok | post_observation |  |
| 74 | ok | post_world_patch |  |
| 75 | fail | transition_eval |  |
| 76 | ok | transition_attribution |  |
| 77 | fail | verification |  |
| 78 | ok | step | app=WhatsApp screenshot=True |
| 79 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 80 | ok | step | sources=['pyobjc_ax', 'macapptree'] agreement=0.7 |
| 81 | ok | observation |  |
| 82 | ok | post_transition_richer_reobserve |  |
| 83 | fail | forward_predicate_rollback |  |
| 84 | ok | step | app=WhatsApp screenshot=True |
| 85 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 86 | ok | step | sources=['pyobjc_ax', 'macapptree'] agreement=0.7 |
| 87 | ok | observation |  |
| 88 | ok | observation |  |
| 89 | ok | forward_task |  |
| 90 | ok | world_patch | dialog |
| 91 | ok | goal_status |  |
| 92 | ok | decision_engine |  |
| 93 | ok | planner_decision |  |
| 94 | ok | step | re-perceive current world (actuation/world uncertainty) |
| 95 | ok | step | app=WhatsApp screenshot=True |
| 96 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 97 | ok | step | sources=['pyobjc_ax', 'macapptree'] agreement=0.7 |
| 98 | ok | observation |  |
| 99 | ok | observation |  |
| 100 | ok | forward_task |  |
| 101 | ok | world_patch | dialog |
| 102 | ok | goal_status |  |
| 103 | ok | decision_engine |  |
| 104 | ok | planner_decision |  |
| 105 | ok | step | re-perceive current world (actuation/world uncertainty) |
| 106 | ok | step | app=WhatsApp screenshot=True |
| 107 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 108 | ok | step | sources=['pyobjc_ax', 'macapptree'] agreement=0.7 |
| 109 | ok | observation |  |
| 110 | ok | observation |  |
| 111 | ok | forward_task |  |
| 112 | ok | world_patch | dialog |
| 113 | ok | goal_status |  |
| 114 | ok | decision_engine |  |
| 115 | ok | planner_decision |  |
| 116 | ok | execution | pressed Escape |
| 117 | ok | step | transition settle |
| 118 | ok | step | app=WhatsApp screenshot=True |
| 119 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 120 | ok | step | sources=['pyobjc_ax', 'macapptree'] agreement=0.7 |
| 121 | ok | observation |  |
| 122 | ok | step | transition poll |
| 123 | ok | step | app=WhatsApp screenshot=True |
| 124 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 125 | ok | step | sources=['pyobjc_ax', 'macapptree'] agreement=0.7 |
| 126 | ok | observation |  |
| 127 | ok | step | transition poll |
| 128 | ok | perception_retry |  |
| 129 | ok | step | perception retry (fusion_agreement_low) |
| 130 | ok | step | app=WhatsApp screenshot=True |
| 131 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 132 | ok | step | sources=['pyobjc_ax', 'macapptree'] agreement=0.7 |
| 133 | ok | observation |  |
| 134 | fail | perception_unsettled |  |
| 135 | ok | post_observation |  |
| 136 | ok | post_world_patch |  |
| 137 | fail | transition_eval |  |
| 138 | ok | transition_attribution |  |
| 139 | fail | verification |  |
| 140 | ok | step | app=WhatsApp screenshot=True |
| 141 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 142 | ok | step | sources=['pyobjc_ax', 'macapptree'] agreement=0.7 |
| 143 | ok | observation |  |
| 144 | ok | post_transition_richer_reobserve |  |
| 145 | fail | forward_predicate_rollback |  |
| 146 | ok | step | app=WhatsApp screenshot=True |
| 147 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 148 | ok | step | sources=['pyobjc_ax', 'macapptree'] agreement=0.7 |
| 149 | ok | observation |  |
| 150 | ok | observation |  |
| 151 | ok | forward_task |  |
| 152 | ok | world_patch | dialog |
| 153 | ok | goal_status |  |
| 154 | ok | decision_engine |  |
| 155 | ok | planner_decision |  |
| 156 | ok | step | re-perceive current world (actuation/world uncertainty) |
| 157 | ok | step | app=WhatsApp screenshot=True |
| 158 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 159 | ok | step | sources=['pyobjc_ax', 'macapptree'] agreement=0.7 |
| 160 | ok | observation |  |
| 161 | ok | observation |  |
| 162 | ok | forward_task |  |
| 163 | ok | world_patch | dialog |
| 164 | ok | goal_status |  |
| 165 | ok | decision_engine |  |
| 166 | ok | planner_decision |  |
| 167 | ok | step | re-perceive current world (actuation/world uncertainty) |
| 168 | ok | step | app=WhatsApp screenshot=True |
| 169 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 170 | ok | step | sources=['pyobjc_ax', 'macapptree'] agreement=0.7 |
| 171 | ok | observation |  |
| 172 | ok | observation |  |
| 173 | ok | forward_task |  |
| 174 | ok | world_patch | dialog |
| 175 | ok | goal_status |  |
| 176 | ok | decision_engine |  |
| 177 | ok | planner_decision |  |
| 178 | ok | execution | pressed Escape |
| 179 | ok | step | transition settle |
| 180 | ok | step | app=WhatsApp screenshot=True |
| 181 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 182 | ok | step | fallback=pyobjc_ax |
| 183 | ok | step | nodes=1 elapsed=0.00s |
| 184 | ok | observation |  |
| 185 | ok | step | transition poll |
| 186 | ok | step | app=WhatsApp screenshot=True |
| 187 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 188 | ok | step | fallback=pyobjc_ax |
| 189 | ok | step | nodes=1 elapsed=0.00s |
| 190 | ok | observation |  |
| 191 | ok | step | transition poll |
| 192 | ok | step | app=WhatsApp screenshot=True |
| 193 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 194 | ok | step | fallback=pyobjc_ax |
| 195 | ok | step | nodes=1 elapsed=0.00s |
| 196 | ok | observation |  |
| 197 | ok | step | transition poll |
| 198 | ok | perception_retry |  |
| 199 | ok | step | perception retry (fusion_agreement_low) |
| 200 | ok | step | app=WhatsApp screenshot=True |
| 201 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 202 | ok | step | fallback=pyobjc_ax |
| 203 | ok | step | nodes=1 elapsed=0.00s |
| 204 | ok | observation |  |
| 205 | fail | perception_unsettled |  |
| 206 | ok | post_observation |  |
| 207 | ok | post_world_patch |  |
| 208 | fail | transition_eval |  |
| 209 | ok | transition_attribution |  |
| 210 | fail | verification |  |
| 211 | ok | step | app=WhatsApp screenshot=True |
| 212 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 213 | ok | step | fallback=pyobjc_ax |
| 214 | ok | step | nodes=1 elapsed=0.00s |
| 215 | ok | observation |  |
| 216 | ok | post_transition_richer_reobserve |  |
| 217 | fail | forward_predicate_rollback |  |
| 218 | ok | step | app=WhatsApp screenshot=True |
| 219 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 220 | ok | step | fallback=pyobjc_ax |
| 221 | ok | step | nodes=1 elapsed=0.00s |
| 222 | ok | observation |  |
| 223 | ok | observation |  |
| 224 | ok | forward_task |  |
| 225 | ok | world_patch | dialog |
| 226 | ok | goal_status |  |
| 227 | ok | decision_engine |  |
| 228 | ok | planner_decision |  |
| 229 | ok | step | re-perceive current world (actuation/world uncertainty) |
| 230 | ok | step | app=WhatsApp screenshot=True |
| 231 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 232 | ok | step | fallback=pyobjc_ax |
| 233 | ok | step | nodes=1 elapsed=0.00s |
| 234 | ok | observation |  |
| 235 | ok | observation |  |
| 236 | ok | forward_task |  |
| 237 | ok | world_patch | dialog |
| 238 | ok | goal_status |  |
| 239 | ok | decision_engine |  |
| 240 | ok | planner_decision |  |
| 241 | ok | step | re-perceive current world (actuation/world uncertainty) |
| 242 | ok | step | app=WhatsApp screenshot=True |
| 243 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 244 | ok | step | fallback=pyobjc_ax |
| 245 | ok | step | nodes=1 elapsed=0.00s |
| 246 | ok | observation |  |
| 247 | ok | observation |  |
| 248 | ok | forward_task |  |
| 249 | ok | world_patch | dialog |
| 250 | ok | goal_status |  |
| 251 | ok | decision_engine |  |
| 252 | ok | planner_decision |  |
| 253 | ok | execution | pressed Escape |
| 254 | ok | step | transition settle |
| 255 | ok | step | app=WhatsApp screenshot=True |
| 256 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 257 | ok | step | fallback=pyobjc_ax |
| 258 | ok | step | nodes=1 elapsed=0.00s |
| 259 | ok | observation |  |
| 260 | ok | step | transition poll |
| 261 | ok | step | app=WhatsApp screenshot=True |
| 262 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 263 | ok | step | fallback=pyobjc_ax |
| 264 | ok | step | nodes=1 elapsed=0.00s |
| 265 | ok | observation |  |
| 266 | ok | step | transition poll |
| 267 | ok | step | app=WhatsApp screenshot=True |
| 268 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 269 | ok | step | fallback=pyobjc_ax |
| 270 | ok | step | nodes=1 elapsed=0.00s |
| 271 | ok | observation |  |
| 272 | ok | step | transition poll |
| 273 | ok | perception_retry |  |
| 274 | ok | step | perception retry (fusion_agreement_low) |
| 275 | ok | step | app=WhatsApp screenshot=True |
| 276 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 277 | ok | step | fallback=pyobjc_ax |
| 278 | ok | step | nodes=1 elapsed=0.00s |
| 279 | ok | observation |  |
| 280 | fail | perception_unsettled |  |
| 281 | ok | post_observation |  |
| 282 | ok | post_world_patch |  |
| 283 | fail | transition_eval |  |
| 284 | ok | transition_attribution |  |
| 285 | fail | verification |  |
| 286 | ok | step | app=WhatsApp screenshot=True |
| 287 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 288 | ok | step | fallback=pyobjc_ax |
| 289 | ok | step | nodes=1 elapsed=0.00s |
| 290 | ok | observation |  |
| 291 | ok | post_transition_richer_reobserve |  |
| 292 | fail | forward_predicate_rollback |  |
| 293 | ok | step | app=WhatsApp screenshot=True |
| 294 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 295 | ok | step | fallback=pyobjc_ax |
| 296 | ok | step | nodes=1 elapsed=0.00s |
| 297 | ok | observation |  |
| 298 | ok | observation |  |
| 299 | ok | forward_task |  |
| 300 | ok | world_patch | dialog |
| 301 | ok | goal_status |  |
| 302 | ok | decision_engine |  |
| 303 | ok | planner_decision |  |
| 304 | ok | step | re-perceive current world (actuation/world uncertainty) |
| 305 | ok | step | app=WhatsApp screenshot=True |
| 306 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 307 | ok | step | fallback=pyobjc_ax |
| 308 | ok | step | nodes=1 elapsed=0.00s |
| 309 | ok | observation |  |
| 310 | ok | observation |  |
| 311 | ok | forward_task |  |
| 312 | ok | world_patch | dialog |
| 313 | ok | goal_status |  |
| 314 | ok | decision_engine |  |
| 315 | ok | planner_decision |  |
| 316 | ok | step | re-perceive current world (actuation/world uncertainty) |
| 317 | ok | step | app=WhatsApp screenshot=True |
| 318 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 319 | ok | step | fallback=pyobjc_ax |
| 320 | ok | step | nodes=1 elapsed=0.00s |
| 321 | ok | observation |  |
| 322 | ok | observation |  |
| 323 | ok | forward_task |  |
| 324 | ok | world_patch | dialog |
| 325 | ok | goal_status |  |
| 326 | ok | decision_engine |  |
| 327 | ok | planner_decision |  |
| 328 | ok | execution | pressed Escape |
| 329 | ok | step | transition settle |
| 330 | ok | step | app=WhatsApp screenshot=True |
| 331 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 332 | ok | step | fallback=pyobjc_ax |
| 333 | ok | step | nodes=1 elapsed=0.00s |
| 334 | ok | observation |  |
| 335 | ok | step | transition poll |
| 336 | ok | step | app=WhatsApp screenshot=True |
| 337 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 338 | ok | step | fallback=pyobjc_ax |
| 339 | ok | step | nodes=1 elapsed=0.00s |
| 340 | ok | observation |  |
| 341 | ok | step | transition poll |
| 342 | ok | step | app=WhatsApp screenshot=True |
| 343 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 344 | ok | step | fallback=pyobjc_ax |
| 345 | ok | step | nodes=1 elapsed=0.01s |
| 346 | ok | observation |  |
| 347 | ok | step | transition poll |
| 348 | ok | perception_retry |  |
| 349 | ok | step | perception retry (fusion_agreement_low) |
| 350 | ok | step | app=WhatsApp screenshot=True |
| 351 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 352 | ok | step | fallback=pyobjc_ax |
| 353 | ok | step | nodes=1 elapsed=0.00s |
| 354 | ok | observation |  |
| 355 | fail | perception_unsettled |  |
| 356 | ok | post_observation |  |
| 357 | ok | post_world_patch |  |
| 358 | fail | transition_eval |  |
| 359 | ok | transition_attribution |  |
| 360 | fail | verification |  |
| 361 | ok | step | app=WhatsApp screenshot=True |
| 362 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 363 | ok | step | fallback=pyobjc_ax |
| 364 | ok | step | nodes=1 elapsed=0.00s |
| 365 | ok | observation |  |
| 366 | ok | post_transition_richer_reobserve |  |
| 367 | fail | forward_predicate_rollback |  |
| 368 | ok | step | app=WhatsApp screenshot=True |
| 369 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 370 | ok | step | fallback=pyobjc_ax |
| 371 | ok | step | nodes=1 elapsed=0.00s |
| 372 | ok | observation |  |
| 373 | ok | observation |  |
| 374 | ok | forward_task |  |
| 375 | ok | world_patch | dialog |
| 376 | ok | goal_status |  |
| 377 | ok | decision_engine |  |
| 378 | ok | planner_decision |  |
| 379 | ok | step | re-perceive current world (actuation/world uncertainty) |
| 380 | ok | step | app=WhatsApp screenshot=True |
| 381 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 382 | ok | step | fallback=pyobjc_ax |
| 383 | ok | step | nodes=1 elapsed=0.00s |
| 384 | ok | observation |  |
| 385 | ok | observation |  |
| 386 | ok | forward_task |  |
| 387 | ok | world_patch | dialog |
| 388 | ok | goal_status |  |
| 389 | ok | decision_engine |  |
| 390 | ok | planner_decision |  |
| 391 | ok | step | re-perceive current world (actuation/world uncertainty) |
| 392 | ok | step | app=WhatsApp screenshot=True |
| 393 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 394 | ok | step | fallback=pyobjc_ax |
| 395 | ok | step | nodes=1 elapsed=0.00s |
| 396 | ok | observation |  |
| 397 | ok | observation |  |
| 398 | ok | forward_task |  |
| 399 | ok | world_patch | dialog |
| 400 | ok | goal_status |  |
| 401 | ok | decision_engine |  |
| 402 | ok | planner_decision |  |
| 403 | ok | execution | pressed Escape |
| 404 | ok | step | transition settle |
| 405 | ok | step | app=WhatsApp screenshot=True |
| 406 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 407 | ok | step | fallback=pyobjc_ax |
| 408 | ok | step | nodes=1 elapsed=0.00s |
| 409 | ok | observation |  |
| 410 | ok | step | transition poll |
| 411 | ok | step | app=WhatsApp screenshot=True |
| 412 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 413 | ok | step | fallback=pyobjc_ax |
| 414 | ok | step | nodes=1 elapsed=0.00s |
| 415 | ok | observation |  |
| 416 | ok | step | transition poll |
| 417 | ok | step | app=WhatsApp screenshot=True |
| 418 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 419 | ok | step | fallback=pyobjc_ax |
| 420 | ok | step | nodes=1 elapsed=0.00s |
| 421 | ok | observation |  |
| 422 | ok | step | transition poll |
| 423 | ok | step | app=WhatsApp screenshot=True |
| 424 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 425 | ok | step | fallback=pyobjc_ax |
| 426 | ok | step | nodes=1 elapsed=0.00s |
| 427 | ok | observation |  |
| 428 | ok | step | transition poll |
| 429 | ok | perception_retry |  |
| 430 | ok | step | perception retry (fusion_agreement_low) |
| 431 | ok | step | app=WhatsApp screenshot=True |
| 432 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 433 | ok | step | fallback=pyobjc_ax |
| 434 | ok | step | nodes=1 elapsed=0.00s |
| 435 | ok | observation |  |
| 436 | fail | perception_unsettled |  |
| 437 | ok | post_observation |  |
| 438 | ok | post_world_patch |  |
| 439 | fail | transition_eval |  |
| 440 | ok | transition_attribution |  |
| 441 | fail | verification |  |
| 442 | ok | step | app=WhatsApp screenshot=True |
| 443 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 444 | ok | step | fallback=pyobjc_ax |
| 445 | ok | step | nodes=1 elapsed=0.00s |
| 446 | ok | observation |  |
| 447 | ok | post_transition_richer_reobserve |  |
| 448 | fail | forward_predicate_rollback |  |
| 449 | ok | step | app=WhatsApp screenshot=True |
| 450 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 451 | ok | step | fallback=pyobjc_ax |
| 452 | ok | step | nodes=1 elapsed=0.00s |
| 453 | ok | observation |  |
| 454 | ok | observation |  |
| 455 | ok | forward_task |  |
| 456 | ok | world_patch | dialog |
| 457 | ok | goal_status |  |
| 458 | ok | decision_engine |  |
| 459 | ok | planner_decision |  |
| 460 | ok | step | re-perceive current world (actuation/world uncertainty) |
| 461 | ok | step | app=WhatsApp screenshot=True |
| 462 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 463 | ok | step | fallback=pyobjc_ax |
| 464 | ok | step | nodes=1 elapsed=0.00s |
| 465 | ok | observation |  |
| 466 | ok | observation |  |
| 467 | ok | forward_task |  |
| 468 | ok | world_patch | dialog |
| 469 | ok | goal_status |  |
| 470 | ok | decision_engine |  |
| 471 | ok | planner_decision |  |
| 472 | ok | step | re-perceive current world (actuation/world uncertainty) |
| 473 | ok | step | app=WhatsApp screenshot=True |
| 474 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 475 | ok | step | fallback=pyobjc_ax |
| 476 | ok | step | nodes=1 elapsed=0.00s |
| 477 | ok | observation |  |
| 478 | ok | observation |  |
| 479 | ok | forward_task |  |
| 480 | ok | world_patch | dialog |
| 481 | ok | goal_status |  |
| 482 | ok | decision_engine |  |
| 483 | ok | planner_decision |  |
| 484 | ok | execution | pressed Escape |
| 485 | ok | step | transition settle |
| 486 | ok | step | app=WhatsApp screenshot=True |
| 487 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 488 | ok | step | fallback=pyobjc_ax |
| 489 | ok | step | nodes=1 elapsed=0.00s |
| 490 | ok | observation |  |
| 491 | ok | step | transition poll |
| 492 | ok | step | app=WhatsApp screenshot=True |
| 493 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 494 | ok | step | fallback=pyobjc_ax |
| 495 | ok | step | nodes=1 elapsed=0.00s |
| 496 | ok | observation |  |
| 497 | ok | step | transition poll |
| 498 | ok | step | app=WhatsApp screenshot=True |
| 499 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 500 | ok | step | fallback=pyobjc_ax |
| 501 | ok | step | nodes=1 elapsed=0.00s |
| 502 | ok | observation |  |
| 503 | ok | step | transition poll |
| 504 | ok | perception_retry |  |
| 505 | ok | step | perception retry (fusion_agreement_low) |
| 506 | ok | step | app=WhatsApp screenshot=True |
| 507 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 508 | ok | step | fallback=pyobjc_ax |
| 509 | ok | step | nodes=1 elapsed=0.00s |
| 510 | ok | observation |  |
| 511 | fail | perception_unsettled |  |
| 512 | ok | post_observation |  |
| 513 | ok | post_world_patch |  |
| 514 | fail | transition_eval |  |
| 515 | ok | transition_attribution |  |
| 516 | fail | verification |  |
| 517 | ok | step | app=WhatsApp screenshot=True |
| 518 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 519 | ok | step | fallback=pyobjc_ax |
| 520 | ok | step | nodes=1 elapsed=0.00s |
| 521 | ok | observation |  |
| 522 | ok | post_transition_richer_reobserve |  |
| 523 | fail | forward_predicate_rollback |  |
| 524 | ok | step | app=WhatsApp screenshot=True |
| 525 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 526 | ok | step | fallback=pyobjc_ax |
| 527 | ok | step | nodes=1 elapsed=0.00s |
| 528 | ok | observation |  |
| 529 | ok | observation |  |
| 530 | ok | forward_task |  |
| 531 | ok | world_patch | dialog |
| 532 | ok | goal_status |  |
| 533 | ok | decision_engine |  |
| 534 | ok | planner_decision |  |
| 535 | ok | step | re-perceive current world (actuation/world uncertainty) |
| 536 | ok | step | app=WhatsApp screenshot=True |
| 537 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 538 | ok | step | fallback=pyobjc_ax |
| 539 | ok | step | nodes=1 elapsed=0.00s |
| 540 | ok | observation |  |
| 541 | ok | observation |  |
| 542 | ok | forward_task |  |
| 543 | ok | world_patch | dialog |
| 544 | ok | goal_status |  |
| 545 | ok | decision_engine |  |
| 546 | ok | planner_decision |  |
| 547 | ok | step | re-perceive current world (actuation/world uncertainty) |
| 548 | ok | step | app=WhatsApp screenshot=True |
| 549 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 550 | ok | step | fallback=pyobjc_ax |
| 551 | ok | step | nodes=1 elapsed=0.00s |
| 552 | ok | observation |  |
| 553 | ok | observation |  |
| 554 | ok | forward_task |  |
| 555 | ok | world_patch | dialog |
| 556 | ok | goal_status |  |
| 557 | ok | decision_engine |  |
| 558 | ok | planner_decision |  |
| 559 | ok | execution | pressed Escape |
| 560 | ok | step | transition settle |
| 561 | ok | step | app=WhatsApp screenshot=True |
| 562 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 563 | ok | step | fallback=pyobjc_ax |
| 564 | ok | step | nodes=1 elapsed=0.00s |
| 565 | ok | observation |  |
| 566 | ok | step | transition poll |
| 567 | ok | step | app=WhatsApp screenshot=True |
| 568 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 569 | ok | step | fallback=pyobjc_ax |
| 570 | ok | step | nodes=1 elapsed=0.00s |
| 571 | ok | observation |  |
| 572 | ok | step | transition poll |
| 573 | ok | perception_retry |  |
| 574 | ok | step | perception retry (fusion_agreement_low) |
| 575 | ok | step | app=WhatsApp screenshot=True |
| 576 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 577 | ok | step | fallback=pyobjc_ax |
| 578 | ok | step | nodes=1 elapsed=0.00s |
| 579 | ok | observation |  |
| 580 | fail | perception_unsettled |  |
| 581 | ok | post_observation |  |
| 582 | ok | post_world_patch |  |
| 583 | fail | transition_eval |  |
| 584 | ok | transition_attribution |  |
| 585 | fail | verification |  |
| 586 | ok | step | app=WhatsApp screenshot=True |
| 587 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 588 | ok | step | fallback=pyobjc_ax |
| 589 | ok | step | nodes=1 elapsed=0.00s |
| 590 | ok | observation |  |
| 591 | ok | post_transition_richer_reobserve |  |
| 592 | fail | forward_predicate_rollback |  |
| 593 | ok | step | app=WhatsApp screenshot=True |
| 594 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 595 | ok | step | fallback=pyobjc_ax |
| 596 | ok | step | nodes=1 elapsed=0.00s |
| 597 | ok | observation |  |
| 598 | ok | observation |  |
| 599 | ok | forward_task |  |
| 600 | ok | world_patch | dialog |
| 601 | ok | goal_status |  |
| 602 | ok | decision_engine |  |
| 603 | ok | planner_decision |  |
| 604 | ok | step | re-perceive current world (actuation/world uncertainty) |
| 605 | ok | step | app=WhatsApp screenshot=True |
| 606 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 607 | ok | step | fallback=pyobjc_ax |
| 608 | ok | step | nodes=1 elapsed=0.00s |
| 609 | ok | observation |  |
| 610 | ok | observation |  |
| 611 | ok | forward_task |  |
| 612 | ok | world_patch | dialog |
| 613 | ok | goal_status |  |
| 614 | ok | decision_engine |  |
| 615 | ok | planner_decision |  |
| 616 | ok | step | re-perceive current world (actuation/world uncertainty) |
| 617 | ok | step | app=WhatsApp screenshot=True |
| 618 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 619 | ok | step | fallback=pyobjc_ax |
| 620 | ok | step | nodes=1 elapsed=0.00s |
| 621 | ok | observation |  |
| 622 | ok | observation |  |
| 623 | ok | forward_task |  |
| 624 | ok | world_patch | dialog |
| 625 | ok | goal_status |  |
| 626 | ok | decision_engine |  |
| 627 | ok | planner_decision |  |
| 628 | ok | execution | pressed Escape |
| 629 | ok | step | transition settle |
| 630 | ok | step | app=WhatsApp screenshot=True |
| 631 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 632 | ok | step | fallback=pyobjc_ax |
| 633 | ok | step | nodes=1 elapsed=0.00s |
| 634 | ok | observation |  |
| 635 | ok | step | transition poll |
| 636 | ok | step | app=WhatsApp screenshot=True |
| 637 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 638 | ok | step | fallback=pyobjc_ax |
| 639 | ok | step | nodes=1 elapsed=0.00s |
| 640 | ok | observation |  |
| 641 | ok | step | transition poll |
| 642 | ok | step | app=WhatsApp screenshot=True |
| 643 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 644 | ok | step | fallback=pyobjc_ax |
| 645 | ok | step | nodes=1 elapsed=0.00s |
| 646 | ok | observation |  |
| 647 | ok | step | transition poll |
| 648 | ok | step | app=WhatsApp screenshot=True |
| 649 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 650 | ok | step | fallback=pyobjc_ax |
| 651 | ok | step | nodes=1 elapsed=0.00s |
| 652 | ok | observation |  |
| 653 | ok | step | transition poll |
| 654 | ok | perception_retry |  |
| 655 | ok | step | perception retry (fusion_agreement_low) |
| 656 | ok | step | app=WhatsApp screenshot=True |
| 657 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 658 | ok | step | fallback=pyobjc_ax |
| 659 | ok | step | nodes=1 elapsed=0.00s |
| 660 | ok | observation |  |
| 661 | fail | perception_unsettled |  |
| 662 | ok | post_observation |  |
| 663 | ok | post_world_patch |  |
| 664 | fail | transition_eval |  |
| 665 | ok | transition_attribution |  |
| 666 | fail | verification |  |
| 667 | ok | step | app=WhatsApp screenshot=True |
| 668 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 669 | ok | step | fallback=pyobjc_ax |
| 670 | ok | step | nodes=1 elapsed=0.00s |
| 671 | ok | observation |  |
| 672 | ok | post_transition_richer_reobserve |  |
| 673 | fail | forward_predicate_rollback |  |
| 674 | ok | step | app=WhatsApp screenshot=True |
| 675 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 676 | ok | step | fallback=pyobjc_ax |
| 677 | ok | step | nodes=1 elapsed=0.00s |
| 678 | ok | observation |  |
| 679 | ok | observation |  |
| 680 | ok | forward_task |  |
| 681 | ok | world_patch | dialog |
| 682 | ok | goal_status |  |
| 683 | ok | decision_engine |  |
| 684 | ok | planner_decision |  |
| 685 | ok | step | re-perceive current world (actuation/world uncertainty) |
| 686 | ok | step | app=WhatsApp screenshot=True |
| 687 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 688 | ok | step | fallback=pyobjc_ax |
| 689 | ok | step | nodes=1 elapsed=0.00s |
| 690 | ok | observation |  |
| 691 | ok | observation |  |
| 692 | ok | forward_task |  |
| 693 | ok | world_patch | dialog |
| 694 | ok | goal_status |  |
| 695 | ok | decision_engine |  |
| 696 | ok | planner_decision |  |
| 697 | ok | step | re-perceive current world (actuation/world uncertainty) |
| 698 | ok | step | app=WhatsApp screenshot=True |
| 699 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 700 | ok | step | fallback=pyobjc_ax |
| 701 | ok | step | nodes=1 elapsed=0.00s |
| 702 | ok | observation |  |
| 703 | ok | observation |  |
| 704 | ok | forward_task |  |
| 705 | ok | world_patch | dialog |
| 706 | ok | goal_status |  |
| 707 | ok | decision_engine |  |
| 708 | ok | planner_decision |  |
| 709 | ok | execution | pressed Escape |
| 710 | ok | step | transition settle |
| 711 | ok | step | app=WhatsApp screenshot=True |
| 712 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 713 | ok | step | fallback=pyobjc_ax |
| 714 | ok | step | nodes=1 elapsed=0.00s |
| 715 | ok | observation |  |
| 716 | ok | step | transition poll |
| 717 | ok | step | app=WhatsApp screenshot=True |
| 718 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 719 | ok | step | fallback=pyobjc_ax |
| 720 | ok | step | nodes=1 elapsed=0.00s |
| 721 | ok | observation |  |
| 722 | ok | step | transition poll |
| 723 | ok | step | app=WhatsApp screenshot=True |
| 724 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 725 | ok | step | fallback=pyobjc_ax |
| 726 | ok | step | nodes=1 elapsed=0.00s |
| 727 | ok | observation |  |
| 728 | ok | step | transition poll |
| 729 | ok | perception_retry |  |
| 730 | ok | step | perception retry (fusion_agreement_low) |
| 731 | ok | step | app=WhatsApp screenshot=True |
| 732 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 733 | ok | step | fallback=pyobjc_ax |
| 734 | ok | step | nodes=1 elapsed=0.00s |
| 735 | ok | observation |  |
| 736 | fail | perception_unsettled |  |
| 737 | ok | post_observation |  |
| 738 | ok | post_world_patch |  |
| 739 | fail | transition_eval |  |
| 740 | ok | transition_attribution |  |
| 741 | fail | verification |  |
| 742 | ok | step | app=WhatsApp screenshot=True |
| 743 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 744 | ok | step | fallback=pyobjc_ax |
| 745 | ok | step | nodes=1 elapsed=0.00s |
| 746 | ok | observation |  |
| 747 | ok | post_transition_richer_reobserve |  |
| 748 | fail | forward_predicate_rollback |  |
| 749 | ok | step | app=WhatsApp screenshot=True |
| 750 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 751 | ok | step | fallback=pyobjc_ax |
| 752 | ok | step | nodes=1 elapsed=0.00s |
| 753 | ok | observation |  |
| 754 | ok | observation |  |
| 755 | ok | forward_task |  |
| 756 | ok | world_patch | dialog |
| 757 | ok | goal_status |  |
| 758 | ok | decision_engine |  |
| 759 | ok | planner_decision |  |
| 760 | ok | step | re-perceive current world (actuation/world uncertainty) |
| 761 | ok | step | app=WhatsApp screenshot=True |
| 762 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 763 | ok | step | fallback=pyobjc_ax |
| 764 | ok | step | nodes=1 elapsed=0.00s |
| 765 | ok | observation |  |
| 766 | ok | observation |  |
| 767 | ok | forward_task |  |
| 768 | ok | world_patch | dialog |
| 769 | ok | goal_status |  |
| 770 | ok | decision_engine |  |
| 771 | ok | planner_decision |  |
| 772 | ok | step | re-perceive current world (actuation/world uncertainty) |
| 773 | ok | step | app=WhatsApp screenshot=True |
| 774 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 775 | ok | step | fallback=pyobjc_ax |
| 776 | ok | step | nodes=1 elapsed=0.00s |
| 777 | ok | observation |  |
| 778 | ok | observation |  |
| 779 | ok | forward_task |  |
| 780 | ok | world_patch | dialog |
| 781 | ok | goal_status |  |
| 782 | ok | decision_engine |  |
| 783 | ok | planner_decision |  |
| 784 | ok | execution | pressed Escape |
| 785 | ok | step | transition settle |
| 786 | ok | step | app=WhatsApp screenshot=True |
| 787 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 788 | ok | step | fallback=pyobjc_ax |
| 789 | ok | step | nodes=1 elapsed=0.00s |
| 790 | ok | observation |  |
| 791 | ok | step | transition poll |
| 792 | ok | step | app=WhatsApp screenshot=True |
| 793 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 794 | ok | step | fallback=pyobjc_ax |
| 795 | ok | step | nodes=1 elapsed=0.00s |
| 796 | ok | observation |  |
| 797 | ok | step | transition poll |
| 798 | ok | step | app=WhatsApp screenshot=True |
| 799 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 800 | ok | step | fallback=pyobjc_ax |
| 801 | ok | step | nodes=1 elapsed=0.00s |
| 802 | ok | observation |  |
| 803 | ok | step | transition poll |
| 804 | ok | perception_retry |  |
| 805 | ok | step | perception retry (fusion_agreement_low) |
| 806 | ok | step | app=WhatsApp screenshot=True |
| 807 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 808 | ok | step | fallback=pyobjc_ax |
| 809 | ok | step | nodes=1 elapsed=0.00s |
| 810 | ok | observation |  |
| 811 | fail | perception_unsettled |  |
| 812 | ok | post_observation |  |
| 813 | ok | post_world_patch |  |
| 814 | fail | transition_eval |  |
| 815 | ok | transition_attribution |  |
| 816 | fail | verification |  |
| 817 | ok | step | app=WhatsApp screenshot=True |
| 818 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 819 | ok | step | fallback=pyobjc_ax |
| 820 | ok | step | nodes=1 elapsed=0.00s |
| 821 | ok | observation |  |
| 822 | ok | post_transition_richer_reobserve |  |
| 823 | fail | forward_predicate_rollback |  |
| 824 | ok | step | app=WhatsApp screenshot=True |
| 825 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 826 | ok | step | fallback=pyobjc_ax |
| 827 | ok | step | nodes=1 elapsed=0.00s |
| 828 | ok | observation |  |
| 829 | ok | observation |  |
| 830 | ok | forward_task |  |
| 831 | ok | world_patch | dialog |
| 832 | ok | goal_status |  |
| 833 | ok | decision_engine |  |
| 834 | ok | planner_decision |  |
| 835 | ok | step | re-perceive current world (actuation/world uncertainty) |
| 836 | ok | step | app=WhatsApp screenshot=True |
| 837 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 838 | ok | step | fallback=pyobjc_ax |
| 839 | ok | step | nodes=1 elapsed=0.00s |
| 840 | ok | observation |  |
| 841 | ok | observation |  |
| 842 | ok | forward_task |  |
| 843 | ok | world_patch | dialog |
| 844 | ok | goal_status |  |
| 845 | ok | decision_engine |  |
| 846 | ok | planner_decision |  |
| 847 | ok | step | re-perceive current world (actuation/world uncertainty) |
| 848 | ok | step | app=WhatsApp screenshot=True |
| 849 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 850 | ok | step | fallback=pyobjc_ax |
| 851 | ok | step | nodes=1 elapsed=0.00s |
| 852 | ok | observation |  |
| 853 | ok | observation |  |
| 854 | ok | forward_task |  |
| 855 | ok | world_patch | dialog |
| 856 | ok | goal_status |  |
| 857 | ok | decision_engine |  |
| 858 | ok | planner_decision |  |
| 859 | ok | execution | pressed Escape |
| 860 | ok | step | transition settle |
| 861 | ok | step | app=WhatsApp screenshot=True |
| 862 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 863 | ok | step | fallback=pyobjc_ax |
| 864 | ok | step | nodes=1 elapsed=0.00s |
| 865 | ok | observation |  |
| 866 | ok | step | transition poll |
| 867 | ok | step | app=WhatsApp screenshot=True |
| 868 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 869 | ok | step | fallback=pyobjc_ax |
| 870 | ok | step | nodes=1 elapsed=0.00s |
| 871 | ok | observation |  |
| 872 | ok | step | transition poll |
| 873 | ok | step | app=WhatsApp screenshot=True |
| 874 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 875 | ok | step | fallback=pyobjc_ax |
| 876 | ok | step | nodes=1 elapsed=0.00s |
| 877 | ok | observation |  |
| 878 | ok | step | transition poll |
| 879 | ok | step | app=WhatsApp screenshot=True |
| 880 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 881 | ok | step | fallback=pyobjc_ax |
| 882 | ok | step | nodes=1 elapsed=0.00s |
| 883 | ok | observation |  |
| 884 | ok | step | transition poll |
| 885 | ok | perception_retry |  |
| 886 | ok | step | perception retry (fusion_agreement_low) |
| 887 | ok | step | app=WhatsApp screenshot=True |
| 888 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 889 | ok | step | fallback=pyobjc_ax |
| 890 | ok | step | nodes=1 elapsed=0.00s |
| 891 | ok | observation |  |
| 892 | fail | perception_unsettled |  |
| 893 | ok | post_observation |  |
| 894 | ok | post_world_patch |  |
| 895 | fail | transition_eval |  |
| 896 | ok | transition_attribution |  |
| 897 | fail | verification |  |
| 898 | ok | step | app=WhatsApp screenshot=True |
| 899 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 900 | ok | step | fallback=pyobjc_ax |
| 901 | ok | step | nodes=1 elapsed=0.00s |
| 902 | ok | observation |  |
| 903 | ok | post_transition_richer_reobserve |  |
| 904 | fail | forward_predicate_rollback |  |
| 905 | ok | step | app=WhatsApp screenshot=True |
| 906 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 907 | ok | step | fallback=pyobjc_ax |
| 908 | ok | step | nodes=1 elapsed=0.00s |
| 909 | ok | observation |  |
| 910 | ok | observation |  |
| 911 | ok | forward_task |  |
| 912 | ok | world_patch | dialog |
| 913 | ok | goal_status |  |
| 914 | ok | decision_engine |  |
| 915 | ok | planner_decision |  |
| 916 | ok | step | re-perceive current world (actuation/world uncertainty) |
| 917 | ok | step | app=WhatsApp screenshot=True |
| 918 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 919 | ok | step | fallback=pyobjc_ax |
| 920 | ok | step | nodes=1 elapsed=0.00s |
| 921 | ok | observation |  |
| 922 | ok | observation |  |
| 923 | ok | forward_task |  |
| 924 | ok | world_patch | dialog |
| 925 | ok | goal_status |  |
| 926 | ok | decision_engine |  |
| 927 | ok | planner_decision |  |
| 928 | ok | step | re-perceive current world (actuation/world uncertainty) |
| 929 | ok | step | app=WhatsApp screenshot=True |
| 930 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 931 | ok | step | fallback=pyobjc_ax |
| 932 | ok | step | nodes=1 elapsed=0.00s |
| 933 | ok | observation |  |
| 934 | ok | observation |  |
| 935 | ok | forward_task |  |
| 936 | ok | world_patch | dialog |
| 937 | ok | goal_status |  |
| 938 | ok | decision_engine |  |
| 939 | ok | planner_decision |  |
| 940 | ok | execution | pressed Escape |
| 941 | ok | step | transition settle |
| 942 | ok | step | app=WhatsApp screenshot=True |
| 943 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 944 | ok | step | fallback=pyobjc_ax |
| 945 | ok | step | nodes=1 elapsed=0.00s |
| 946 | ok | observation |  |
| 947 | ok | step | transition poll |
| 948 | ok | step | app=WhatsApp screenshot=True |
| 949 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 950 | ok | step | fallback=pyobjc_ax |
| 951 | ok | step | nodes=1 elapsed=0.00s |
| 952 | ok | observation |  |
| 953 | ok | step | transition poll |
| 954 | ok | step | app=WhatsApp screenshot=True |
| 955 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 956 | ok | step | fallback=pyobjc_ax |
| 957 | ok | step | nodes=1 elapsed=0.00s |
| 958 | ok | observation |  |
| 959 | ok | step | transition poll |
| 960 | ok | perception_retry |  |
| 961 | ok | step | perception retry (fusion_agreement_low) |
| 962 | ok | step | app=WhatsApp screenshot=True |
| 963 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 964 | ok | step | fallback=pyobjc_ax |
| 965 | ok | step | nodes=1 elapsed=0.00s |
| 966 | ok | observation |  |
| 967 | fail | perception_unsettled |  |
| 968 | ok | post_observation |  |
| 969 | ok | post_world_patch |  |
| 970 | fail | transition_eval |  |
| 971 | ok | transition_attribution |  |
| 972 | fail | verification |  |
| 973 | ok | step | app=WhatsApp screenshot=True |
| 974 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 975 | ok | step | fallback=pyobjc_ax |
| 976 | ok | step | nodes=1 elapsed=0.00s |
| 977 | ok | observation |  |
| 978 | ok | post_transition_richer_reobserve |  |
| 979 | fail | forward_predicate_rollback |  |
| 980 | ok | step | app=WhatsApp screenshot=True |
| 981 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 982 | ok | step | fallback=pyobjc_ax |
| 983 | ok | step | nodes=1 elapsed=0.00s |
| 984 | ok | observation |  |
| 985 | ok | observation |  |
| 986 | ok | forward_task |  |
| 987 | ok | world_patch | dialog |
| 988 | ok | goal_status |  |
| 989 | ok | decision_engine |  |
| 990 | ok | planner_decision |  |
| 991 | ok | step | re-perceive current world (actuation/world uncertainty) |
| 992 | ok | step | app=WhatsApp screenshot=True |
| 993 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 994 | ok | step | fallback=pyobjc_ax |
| 995 | ok | step | nodes=1 elapsed=0.00s |
| 996 | ok | observation |  |
| 997 | ok | observation |  |
| 998 | ok | forward_task |  |
| 999 | ok | world_patch | dialog |
| 1000 | ok | goal_status |  |
| 1001 | ok | decision_engine |  |
| 1002 | ok | planner_decision |  |
| 1003 | ok | step | re-perceive current world (actuation/world uncertainty) |
| 1004 | ok | step | app=WhatsApp screenshot=True |
| 1005 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1006 | ok | step | fallback=pyobjc_ax |
| 1007 | ok | step | nodes=1 elapsed=0.00s |
| 1008 | ok | observation |  |
| 1009 | ok | observation |  |
| 1010 | ok | forward_task |  |
| 1011 | ok | world_patch | dialog |
| 1012 | ok | goal_status |  |
| 1013 | ok | decision_engine |  |
| 1014 | ok | planner_decision |  |
| 1015 | ok | execution | pressed Escape |
| 1016 | ok | step | transition settle |
| 1017 | ok | step | app=WhatsApp screenshot=True |
| 1018 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1019 | ok | step | fallback=pyobjc_ax |
| 1020 | ok | step | nodes=1 elapsed=0.00s |
| 1021 | ok | observation |  |
| 1022 | ok | step | transition poll |
| 1023 | ok | step | app=WhatsApp screenshot=True |
| 1024 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1025 | ok | step | fallback=pyobjc_ax |
| 1026 | ok | step | nodes=1 elapsed=0.00s |
| 1027 | ok | observation |  |
| 1028 | ok | step | transition poll |
| 1029 | ok | step | app=WhatsApp screenshot=True |
| 1030 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1031 | ok | step | fallback=pyobjc_ax |
| 1032 | ok | step | nodes=1 elapsed=0.00s |
| 1033 | ok | observation |  |
| 1034 | ok | step | transition poll |
| 1035 | ok | perception_retry |  |
| 1036 | ok | step | perception retry (fusion_agreement_low) |
| 1037 | ok | step | app=WhatsApp screenshot=True |
| 1038 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1039 | ok | step | fallback=pyobjc_ax |
| 1040 | ok | step | nodes=1 elapsed=0.00s |
| 1041 | ok | observation |  |
| 1042 | fail | perception_unsettled |  |
| 1043 | ok | post_observation |  |
| 1044 | ok | post_world_patch |  |
| 1045 | fail | transition_eval |  |
| 1046 | ok | transition_attribution |  |
| 1047 | fail | verification |  |
| 1048 | ok | step | app=WhatsApp screenshot=True |
| 1049 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1050 | ok | step | fallback=pyobjc_ax |
| 1051 | ok | step | nodes=1 elapsed=0.00s |
| 1052 | ok | observation |  |
| 1053 | ok | post_transition_richer_reobserve |  |
| 1054 | fail | forward_predicate_rollback |  |
| 1055 | ok | step | app=WhatsApp screenshot=True |
| 1056 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1057 | ok | step | fallback=pyobjc_ax |
| 1058 | ok | step | nodes=1 elapsed=0.00s |
| 1059 | ok | observation |  |
| 1060 | ok | observation |  |
| 1061 | ok | forward_task |  |
| 1062 | ok | world_patch | dialog |
| 1063 | ok | goal_status |  |
| 1064 | ok | decision_engine |  |
| 1065 | ok | planner_decision |  |
| 1066 | ok | step | re-perceive current world (actuation/world uncertainty) |
| 1067 | ok | step | app=WhatsApp screenshot=True |
| 1068 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1069 | ok | step | fallback=pyobjc_ax |
| 1070 | ok | step | nodes=1 elapsed=0.00s |
| 1071 | ok | observation |  |
| 1072 | ok | observation |  |
| 1073 | ok | forward_task |  |
| 1074 | ok | world_patch | dialog |
| 1075 | ok | goal_status |  |
| 1076 | ok | decision_engine |  |
| 1077 | ok | planner_decision |  |
| 1078 | ok | step | re-perceive current world (actuation/world uncertainty) |
| 1079 | ok | step | app=WhatsApp screenshot=True |
| 1080 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1081 | ok | step | fallback=pyobjc_ax |
| 1082 | ok | step | nodes=1 elapsed=0.00s |
| 1083 | ok | observation |  |
| 1084 | ok | observation |  |
| 1085 | ok | forward_task |  |
| 1086 | ok | world_patch | dialog |
| 1087 | ok | goal_status |  |
| 1088 | ok | decision_engine |  |
| 1089 | ok | planner_decision |  |
| 1090 | ok | execution | pressed Escape |
| 1091 | ok | step | transition settle |
| 1092 | ok | step | app=WhatsApp screenshot=True |
| 1093 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1094 | ok | step | fallback=pyobjc_ax |
| 1095 | ok | step | nodes=1 elapsed=0.00s |
| 1096 | ok | observation |  |
| 1097 | ok | step | transition poll |
| 1098 | ok | step | app=WhatsApp screenshot=True |
| 1099 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1100 | ok | step | fallback=pyobjc_ax |
| 1101 | ok | step | nodes=1 elapsed=0.00s |
| 1102 | ok | observation |  |
| 1103 | ok | step | transition poll |
| 1104 | ok | step | app=WhatsApp screenshot=True |
| 1105 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1106 | ok | step | fallback=pyobjc_ax |
| 1107 | ok | step | nodes=1 elapsed=0.00s |
| 1108 | ok | observation |  |
| 1109 | ok | step | transition poll |
| 1110 | ok | step | app=WhatsApp screenshot=True |
| 1111 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1112 | ok | step | fallback=pyobjc_ax |
| 1113 | ok | step | nodes=1 elapsed=0.00s |
| 1114 | ok | observation |  |
| 1115 | ok | step | transition poll |
| 1116 | ok | perception_retry |  |
| 1117 | ok | step | perception retry (fusion_agreement_low) |
| 1118 | ok | step | app=WhatsApp screenshot=True |
| 1119 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1120 | ok | step | fallback=pyobjc_ax |
| 1121 | ok | step | nodes=1 elapsed=0.00s |
| 1122 | ok | observation |  |
| 1123 | fail | perception_unsettled |  |
| 1124 | ok | post_observation |  |
| 1125 | ok | post_world_patch |  |
| 1126 | fail | transition_eval |  |
| 1127 | ok | transition_attribution |  |
| 1128 | fail | verification |  |
| 1129 | ok | step | app=WhatsApp screenshot=True |
| 1130 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1131 | ok | step | fallback=pyobjc_ax |
| 1132 | ok | step | nodes=1 elapsed=0.00s |
| 1133 | ok | observation |  |
| 1134 | ok | post_transition_richer_reobserve |  |
| 1135 | fail | forward_predicate_rollback |  |
| 1136 | ok | step | app=WhatsApp screenshot=True |
| 1137 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1138 | ok | step | fallback=pyobjc_ax |
| 1139 | ok | step | nodes=1 elapsed=0.00s |
| 1140 | ok | observation |  |
| 1141 | ok | observation |  |
| 1142 | ok | forward_task |  |
| 1143 | ok | world_patch | dialog |
| 1144 | ok | goal_status |  |
| 1145 | ok | decision_engine |  |
| 1146 | ok | planner_decision |  |
| 1147 | ok | step | re-perceive current world (actuation/world uncertainty) |
| 1148 | ok | step | app=WhatsApp screenshot=True |
| 1149 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1150 | ok | step | fallback=pyobjc_ax |
| 1151 | ok | step | nodes=1 elapsed=0.00s |
| 1152 | ok | observation |  |
| 1153 | ok | observation |  |
| 1154 | ok | forward_task |  |
| 1155 | ok | world_patch | dialog |
| 1156 | ok | goal_status |  |
| 1157 | ok | decision_engine |  |
| 1158 | ok | planner_decision |  |
| 1159 | ok | step | re-perceive current world (actuation/world uncertainty) |
| 1160 | ok | step | app=WhatsApp screenshot=True |
| 1161 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1162 | ok | step | fallback=pyobjc_ax |
| 1163 | ok | step | nodes=1 elapsed=0.00s |
| 1164 | ok | observation |  |
| 1165 | ok | observation |  |
| 1166 | ok | forward_task |  |
| 1167 | ok | world_patch | dialog |
| 1168 | ok | goal_status |  |
| 1169 | ok | decision_engine |  |
| 1170 | ok | planner_decision |  |
| 1171 | ok | execution | pressed Escape |
| 1172 | ok | step | transition settle |
| 1173 | ok | step | app=WhatsApp screenshot=True |
| 1174 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1175 | ok | step | fallback=pyobjc_ax |
| 1176 | ok | step | nodes=1 elapsed=0.00s |
| 1177 | ok | observation |  |
| 1178 | ok | step | transition poll |
| 1179 | ok | step | app=WhatsApp screenshot=True |
| 1180 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1181 | ok | step | fallback=pyobjc_ax |
| 1182 | ok | step | nodes=1 elapsed=0.00s |
| 1183 | ok | observation |  |
| 1184 | ok | step | transition poll |
| 1185 | ok | step | app=WhatsApp screenshot=True |
| 1186 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1187 | ok | step | fallback=pyobjc_ax |
| 1188 | ok | step | nodes=1 elapsed=0.00s |
| 1189 | ok | observation |  |
| 1190 | ok | step | transition poll |
| 1191 | ok | perception_retry |  |
| 1192 | ok | step | perception retry (fusion_agreement_low) |
| 1193 | ok | step | app=WhatsApp screenshot=True |
| 1194 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1195 | ok | step | fallback=pyobjc_ax |
| 1196 | ok | step | nodes=1 elapsed=0.00s |
| 1197 | ok | observation |  |
| 1198 | fail | perception_unsettled |  |
| 1199 | ok | post_observation |  |
| 1200 | ok | post_world_patch |  |
| 1201 | fail | transition_eval |  |
| 1202 | ok | transition_attribution |  |
| 1203 | fail | verification |  |
| 1204 | ok | step | app=WhatsApp screenshot=True |
| 1205 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1206 | ok | step | fallback=pyobjc_ax |
| 1207 | ok | step | nodes=1 elapsed=0.00s |
| 1208 | ok | observation |  |
| 1209 | ok | post_transition_richer_reobserve |  |
| 1210 | fail | forward_predicate_rollback |  |
| 1211 | ok | step | app=WhatsApp screenshot=True |
| 1212 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1213 | ok | step | fallback=pyobjc_ax |
| 1214 | ok | step | nodes=1 elapsed=0.00s |
| 1215 | ok | observation |  |
| 1216 | ok | observation |  |
| 1217 | ok | forward_task |  |
| 1218 | ok | world_patch | dialog |
| 1219 | ok | goal_status |  |
| 1220 | ok | decision_engine |  |
| 1221 | ok | planner_decision |  |
| 1222 | ok | step | re-perceive current world (actuation/world uncertainty) |
| 1223 | ok | step | app=WhatsApp screenshot=True |
| 1224 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1225 | ok | step | fallback=pyobjc_ax |
| 1226 | ok | step | nodes=1 elapsed=0.00s |
| 1227 | ok | observation |  |
| 1228 | ok | observation |  |
| 1229 | ok | forward_task |  |
| 1230 | ok | world_patch | dialog |
| 1231 | ok | goal_status |  |
| 1232 | ok | decision_engine |  |
| 1233 | ok | planner_decision |  |
| 1234 | ok | step | re-perceive current world (actuation/world uncertainty) |
| 1235 | ok | step | app=WhatsApp screenshot=True |
| 1236 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1237 | ok | step | fallback=pyobjc_ax |
| 1238 | ok | step | nodes=1 elapsed=0.00s |
| 1239 | ok | observation |  |
| 1240 | ok | observation |  |
| 1241 | ok | forward_task |  |
| 1242 | ok | world_patch | dialog |
| 1243 | ok | goal_status |  |
| 1244 | ok | decision_engine |  |
| 1245 | ok | planner_decision |  |
| 1246 | ok | execution | pressed Escape |
| 1247 | ok | step | transition settle |
| 1248 | ok | step | app=WhatsApp screenshot=True |
| 1249 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1250 | ok | step | fallback=pyobjc_ax |
| 1251 | ok | step | nodes=1 elapsed=0.00s |
| 1252 | ok | observation |  |
| 1253 | ok | step | transition poll |
| 1254 | ok | step | app=WhatsApp screenshot=True |
| 1255 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1256 | ok | step | fallback=pyobjc_ax |
| 1257 | ok | step | nodes=1 elapsed=0.00s |
| 1258 | ok | observation |  |
| 1259 | ok | step | transition poll |
| 1260 | ok | step | app=WhatsApp screenshot=True |
| 1261 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1262 | ok | step | fallback=pyobjc_ax |
| 1263 | ok | step | nodes=1 elapsed=0.00s |
| 1264 | ok | observation |  |
| 1265 | ok | step | transition poll |
| 1266 | ok | step | app=WhatsApp screenshot=True |
| 1267 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1268 | ok | step | fallback=pyobjc_ax |
| 1269 | ok | step | nodes=1 elapsed=0.00s |
| 1270 | ok | observation |  |
| 1271 | ok | step | transition poll |
| 1272 | ok | perception_retry |  |
| 1273 | ok | step | perception retry (fusion_agreement_low) |
| 1274 | ok | step | app=WhatsApp screenshot=True |
| 1275 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1276 | ok | step | fallback=pyobjc_ax |
| 1277 | ok | step | nodes=1 elapsed=0.00s |
| 1278 | ok | observation |  |
| 1279 | fail | perception_unsettled |  |
| 1280 | ok | post_observation |  |
| 1281 | ok | post_world_patch |  |
| 1282 | fail | transition_eval |  |
| 1283 | ok | transition_attribution |  |
| 1284 | fail | verification |  |
| 1285 | ok | step | app=WhatsApp screenshot=True |
| 1286 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1287 | ok | step | fallback=pyobjc_ax |
| 1288 | ok | step | nodes=1 elapsed=0.00s |
| 1289 | ok | observation |  |
| 1290 | ok | post_transition_richer_reobserve |  |
| 1291 | fail | forward_predicate_rollback |  |
| 1292 | ok | step | app=WhatsApp screenshot=True |
| 1293 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1294 | ok | step | fallback=pyobjc_ax |
| 1295 | ok | step | nodes=1 elapsed=0.00s |
| 1296 | ok | observation |  |
| 1297 | ok | observation |  |
| 1298 | ok | forward_task |  |
| 1299 | ok | world_patch | dialog |
| 1300 | ok | goal_status |  |
| 1301 | ok | decision_engine |  |
| 1302 | ok | planner_decision |  |
| 1303 | ok | step | re-perceive current world (actuation/world uncertainty) |
| 1304 | ok | step | app=WhatsApp screenshot=True |
| 1305 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1306 | ok | step | fallback=pyobjc_ax |
| 1307 | ok | step | nodes=1 elapsed=0.00s |
| 1308 | ok | observation |  |
| 1309 | ok | observation |  |
| 1310 | ok | forward_task |  |
| 1311 | ok | world_patch | dialog |
| 1312 | ok | goal_status |  |
| 1313 | ok | decision_engine |  |
| 1314 | ok | planner_decision |  |
| 1315 | ok | step | re-perceive current world (actuation/world uncertainty) |
| 1316 | ok | step | app=WhatsApp screenshot=True |
| 1317 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1318 | ok | step | fallback=pyobjc_ax |
| 1319 | ok | step | nodes=1 elapsed=0.02s |
| 1320 | ok | observation |  |
| 1321 | ok | observation |  |
| 1322 | ok | forward_task |  |
| 1323 | ok | world_patch | dialog |
| 1324 | ok | goal_status |  |
| 1325 | ok | decision_engine |  |
| 1326 | ok | planner_decision |  |
| 1327 | ok | execution | pressed Escape |
| 1328 | ok | step | transition settle |
| 1329 | ok | step | app=WhatsApp screenshot=True |
| 1330 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1331 | ok | step | fallback=pyobjc_ax |
| 1332 | ok | step | nodes=1 elapsed=0.00s |
| 1333 | ok | observation |  |
| 1334 | ok | step | transition poll |
| 1335 | ok | step | app=WhatsApp screenshot=True |
| 1336 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1337 | ok | step | fallback=pyobjc_ax |
| 1338 | ok | step | nodes=1 elapsed=0.00s |
| 1339 | ok | observation |  |
| 1340 | ok | step | transition poll |
| 1341 | ok | step | app=WhatsApp screenshot=True |
| 1342 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1343 | ok | step | fallback=pyobjc_ax |
| 1344 | ok | step | nodes=1 elapsed=0.01s |
| 1345 | ok | observation |  |
| 1346 | ok | step | transition poll |
| 1347 | ok | perception_retry |  |
| 1348 | ok | step | perception retry (fusion_agreement_low) |
| 1349 | ok | step | app=WhatsApp screenshot=True |
| 1350 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1351 | ok | step | fallback=pyobjc_ax |
| 1352 | ok | step | nodes=1 elapsed=0.00s |
| 1353 | ok | observation |  |
| 1354 | fail | perception_unsettled |  |
| 1355 | ok | post_observation |  |
| 1356 | ok | post_world_patch |  |
| 1357 | fail | transition_eval |  |
| 1358 | ok | transition_attribution |  |
| 1359 | fail | verification |  |
| 1360 | ok | step | app=WhatsApp screenshot=True |
| 1361 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1362 | ok | step | fallback=pyobjc_ax |
| 1363 | ok | step | nodes=1 elapsed=0.00s |
| 1364 | ok | observation |  |
| 1365 | ok | post_transition_richer_reobserve |  |
| 1366 | fail | forward_predicate_rollback |  |
| 1367 | ok | step | app=WhatsApp screenshot=True |
| 1368 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1369 | ok | step | fallback=pyobjc_ax |
| 1370 | ok | step | nodes=1 elapsed=0.00s |
| 1371 | ok | observation |  |
| 1372 | ok | observation |  |
| 1373 | ok | forward_task |  |
| 1374 | ok | world_patch | dialog |
| 1375 | ok | goal_status |  |
| 1376 | ok | decision_engine |  |
| 1377 | ok | planner_decision |  |
| 1378 | ok | step | re-perceive current world (actuation/world uncertainty) |
| 1379 | ok | step | app=WhatsApp screenshot=True |
| 1380 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1381 | ok | step | fallback=pyobjc_ax |
| 1382 | ok | step | nodes=1 elapsed=0.00s |
| 1383 | ok | observation |  |
| 1384 | ok | observation |  |
| 1385 | ok | forward_task |  |
| 1386 | ok | world_patch | dialog |
| 1387 | ok | goal_status |  |
| 1388 | ok | decision_engine |  |
| 1389 | ok | planner_decision |  |
| 1390 | ok | step | re-perceive current world (actuation/world uncertainty) |
| 1391 | ok | step | app=WhatsApp screenshot=True |
| 1392 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1393 | ok | step | fallback=pyobjc_ax |
| 1394 | ok | step | nodes=1 elapsed=0.00s |
| 1395 | ok | observation |  |
| 1396 | ok | observation |  |
| 1397 | ok | forward_task |  |
| 1398 | ok | world_patch | dialog |
| 1399 | ok | goal_status |  |
| 1400 | ok | decision_engine |  |
| 1401 | ok | planner_decision |  |
| 1402 | ok | execution | pressed Escape |
| 1403 | ok | step | transition settle |
| 1404 | ok | step | app=WhatsApp screenshot=True |
| 1405 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1406 | ok | step | fallback=pyobjc_ax |
| 1407 | ok | step | nodes=1 elapsed=0.00s |
| 1408 | ok | observation |  |
| 1409 | ok | step | transition poll |
| 1410 | ok | step | app=WhatsApp screenshot=True |
| 1411 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1412 | ok | step | fallback=pyobjc_ax |
| 1413 | ok | step | nodes=1 elapsed=0.00s |
| 1414 | ok | observation |  |
| 1415 | ok | step | transition poll |
| 1416 | ok | step | app=WhatsApp screenshot=True |
| 1417 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1418 | ok | step | fallback=pyobjc_ax |
| 1419 | ok | step | nodes=1 elapsed=0.00s |
| 1420 | ok | observation |  |
| 1421 | ok | step | transition poll |
| 1422 | ok | step | app=WhatsApp screenshot=True |
| 1423 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1424 | ok | step | fallback=pyobjc_ax |
| 1425 | ok | step | nodes=1 elapsed=0.00s |
| 1426 | ok | observation |  |
| 1427 | ok | step | transition poll |
| 1428 | ok | perception_retry |  |
| 1429 | ok | step | perception retry (fusion_agreement_low) |
| 1430 | ok | step | app=WhatsApp screenshot=True |
| 1431 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1432 | ok | step | fallback=pyobjc_ax |
| 1433 | ok | step | nodes=1 elapsed=0.00s |
| 1434 | ok | observation |  |
| 1435 | fail | perception_unsettled |  |
| 1436 | ok | post_observation |  |
| 1437 | ok | post_world_patch |  |
| 1438 | fail | transition_eval |  |
| 1439 | ok | transition_attribution |  |
| 1440 | fail | verification |  |
| 1441 | ok | step | app=WhatsApp screenshot=True |
| 1442 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1443 | ok | step | fallback=pyobjc_ax |
| 1444 | ok | step | nodes=1 elapsed=0.00s |
| 1445 | ok | observation |  |
| 1446 | ok | post_transition_richer_reobserve |  |
| 1447 | fail | forward_predicate_rollback |  |
| 1448 | ok | step | app=WhatsApp screenshot=True |
| 1449 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1450 | ok | step | fallback=pyobjc_ax |
| 1451 | ok | step | nodes=1 elapsed=0.00s |
| 1452 | ok | observation |  |
| 1453 | ok | observation |  |
| 1454 | ok | forward_task |  |
| 1455 | ok | world_patch | dialog |
| 1456 | ok | goal_status |  |
| 1457 | ok | decision_engine |  |
| 1458 | ok | planner_decision |  |
| 1459 | ok | step | re-perceive current world (actuation/world uncertainty) |
| 1460 | ok | step | app=WhatsApp screenshot=True |
| 1461 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1462 | ok | step | fallback=pyobjc_ax |
| 1463 | ok | step | nodes=1 elapsed=0.00s |
| 1464 | ok | observation |  |
| 1465 | ok | observation |  |
| 1466 | ok | forward_task |  |
| 1467 | ok | world_patch | dialog |
| 1468 | ok | goal_status |  |
| 1469 | ok | decision_engine |  |
| 1470 | ok | planner_decision |  |
| 1471 | ok | step | re-perceive current world (actuation/world uncertainty) |
| 1472 | ok | step | app=WhatsApp screenshot=True |
| 1473 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1474 | ok | step | fallback=pyobjc_ax |
| 1475 | ok | step | nodes=1 elapsed=0.00s |
| 1476 | ok | observation |  |
| 1477 | ok | observation |  |
| 1478 | ok | forward_task |  |
| 1479 | ok | world_patch | dialog |
| 1480 | ok | goal_status |  |
| 1481 | ok | decision_engine |  |
| 1482 | ok | planner_decision |  |
| 1483 | ok | execution | pressed Escape |
| 1484 | ok | step | transition settle |
| 1485 | ok | step | app=WhatsApp screenshot=True |
| 1486 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1487 | ok | step | fallback=pyobjc_ax |
| 1488 | ok | step | nodes=1 elapsed=0.00s |
| 1489 | ok | observation |  |
| 1490 | ok | step | transition poll |
| 1491 | ok | step | app=WhatsApp screenshot=True |
| 1492 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1493 | ok | step | fallback=pyobjc_ax |
| 1494 | ok | step | nodes=1 elapsed=0.00s |
| 1495 | ok | observation |  |
| 1496 | ok | step | transition poll |
| 1497 | ok | perception_retry |  |
| 1498 | ok | step | perception retry (fusion_agreement_low) |
| 1499 | ok | step | app=WhatsApp screenshot=True |
| 1500 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1501 | ok | step | fallback=pyobjc_ax |
| 1502 | ok | step | nodes=1 elapsed=0.00s |
| 1503 | ok | observation |  |
| 1504 | fail | perception_unsettled |  |
| 1505 | ok | post_observation |  |
| 1506 | ok | post_world_patch |  |
| 1507 | fail | transition_eval |  |
| 1508 | ok | transition_attribution |  |
| 1509 | fail | verification |  |
| 1510 | ok | step | app=WhatsApp screenshot=True |
| 1511 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1512 | ok | step | fallback=pyobjc_ax |
| 1513 | ok | step | nodes=1 elapsed=0.00s |
| 1514 | ok | observation |  |
| 1515 | ok | post_transition_richer_reobserve |  |
| 1516 | fail | forward_predicate_rollback |  |
| 1517 | ok | step | app=WhatsApp screenshot=True |
| 1518 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1519 | ok | step | fallback=pyobjc_ax |
| 1520 | ok | step | nodes=1 elapsed=0.00s |
| 1521 | ok | observation |  |
| 1522 | ok | observation |  |
| 1523 | ok | forward_task |  |
| 1524 | ok | world_patch | dialog |
| 1525 | ok | goal_status |  |
| 1526 | ok | decision_engine |  |
| 1527 | ok | planner_decision |  |
| 1528 | ok | step | re-perceive current world (actuation/world uncertainty) |
| 1529 | ok | step | app=WhatsApp screenshot=True |
| 1530 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1531 | ok | step | fallback=pyobjc_ax |
| 1532 | ok | step | nodes=1 elapsed=0.00s |
| 1533 | ok | observation |  |
| 1534 | ok | observation |  |
| 1535 | ok | forward_task |  |
| 1536 | ok | world_patch | dialog |
| 1537 | ok | goal_status |  |
| 1538 | ok | decision_engine |  |
| 1539 | ok | planner_decision |  |
| 1540 | ok | step | re-perceive current world (actuation/world uncertainty) |
| 1541 | ok | step | app=WhatsApp screenshot=True |
| 1542 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1543 | ok | step | fallback=pyobjc_ax |
| 1544 | ok | step | nodes=1 elapsed=0.00s |
| 1545 | ok | observation |  |
| 1546 | ok | observation |  |
| 1547 | ok | forward_task |  |
| 1548 | ok | world_patch | dialog |
| 1549 | ok | goal_status |  |
| 1550 | ok | decision_engine |  |
| 1551 | ok | planner_decision |  |
| 1552 | ok | execution | pressed Escape |
| 1553 | ok | step | transition settle |
| 1554 | ok | step | app=WhatsApp screenshot=True |
| 1555 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1556 | ok | step | fallback=pyobjc_ax |
| 1557 | ok | step | nodes=1 elapsed=0.00s |
| 1558 | ok | observation |  |
| 1559 | ok | step | transition poll |
| 1560 | ok | step | app=WhatsApp screenshot=True |
| 1561 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1562 | ok | step | fallback=pyobjc_ax |
| 1563 | ok | step | nodes=1 elapsed=0.00s |
| 1564 | ok | observation |  |
| 1565 | ok | step | transition poll |
| 1566 | ok | step | app=WhatsApp screenshot=True |
| 1567 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1568 | ok | step | fallback=pyobjc_ax |
| 1569 | ok | step | nodes=1 elapsed=0.00s |
| 1570 | ok | observation |  |
| 1571 | ok | step | transition poll |
| 1572 | ok | step | app=WhatsApp screenshot=True |
| 1573 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1574 | ok | step | fallback=pyobjc_ax |
| 1575 | ok | step | nodes=1 elapsed=0.00s |
| 1576 | ok | observation |  |
| 1577 | ok | step | transition poll |
| 1578 | ok | perception_retry |  |
| 1579 | ok | step | perception retry (fusion_agreement_low) |
| 1580 | ok | step | app=WhatsApp screenshot=True |
| 1581 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1582 | ok | step | fallback=pyobjc_ax |
| 1583 | ok | step | nodes=1 elapsed=0.00s |
| 1584 | ok | observation |  |
| 1585 | fail | perception_unsettled |  |
| 1586 | ok | post_observation |  |
| 1587 | ok | post_world_patch |  |
| 1588 | fail | transition_eval |  |
| 1589 | ok | transition_attribution |  |
| 1590 | fail | verification |  |
| 1591 | ok | step | app=WhatsApp screenshot=True |
| 1592 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1593 | ok | step | fallback=pyobjc_ax |
| 1594 | ok | step | nodes=1 elapsed=0.00s |
| 1595 | ok | observation |  |
| 1596 | ok | post_transition_richer_reobserve |  |
| 1597 | fail | forward_predicate_rollback |  |
| 1598 | ok | step | app=WhatsApp screenshot=True |
| 1599 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1600 | ok | step | fallback=pyobjc_ax |
| 1601 | ok | step | nodes=1 elapsed=0.00s |
| 1602 | ok | observation |  |
| 1603 | ok | observation |  |
| 1604 | ok | forward_task |  |
| 1605 | ok | world_patch | dialog |
| 1606 | ok | goal_status |  |
| 1607 | ok | decision_engine |  |
| 1608 | ok | planner_decision |  |
| 1609 | ok | step | re-perceive current world (actuation/world uncertainty) |
| 1610 | ok | step | app=WhatsApp screenshot=True |
| 1611 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1612 | ok | step | fallback=pyobjc_ax |
| 1613 | ok | step | nodes=1 elapsed=0.00s |
| 1614 | ok | observation |  |
| 1615 | ok | observation |  |
| 1616 | ok | forward_task |  |
| 1617 | ok | world_patch | dialog |
| 1618 | ok | goal_status |  |
| 1619 | ok | decision_engine |  |
| 1620 | ok | planner_decision |  |
| 1621 | ok | step | re-perceive current world (actuation/world uncertainty) |
| 1622 | ok | step | app=WhatsApp screenshot=True |
| 1623 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1624 | ok | step | fallback=pyobjc_ax |
| 1625 | ok | step | nodes=1 elapsed=0.00s |
| 1626 | ok | observation |  |
| 1627 | ok | observation |  |
| 1628 | ok | forward_task |  |
| 1629 | ok | world_patch | dialog |
| 1630 | ok | goal_status |  |
| 1631 | ok | decision_engine |  |
| 1632 | ok | planner_decision |  |
| 1633 | ok | execution | pressed Escape |
| 1634 | ok | step | transition settle |
| 1635 | ok | step | app=WhatsApp screenshot=True |
| 1636 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1637 | ok | step | fallback=pyobjc_ax |
| 1638 | ok | step | nodes=1 elapsed=0.00s |
| 1639 | ok | observation |  |
| 1640 | ok | step | transition poll |
| 1641 | ok | step | app=WhatsApp screenshot=True |
| 1642 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1643 | ok | step | fallback=pyobjc_ax |
| 1644 | ok | step | nodes=1 elapsed=0.00s |
| 1645 | ok | observation |  |
| 1646 | ok | step | transition poll |
| 1647 | ok | step | app=WhatsApp screenshot=True |
| 1648 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1649 | ok | step | fallback=pyobjc_ax |
| 1650 | ok | step | nodes=1 elapsed=0.00s |
| 1651 | ok | observation |  |
| 1652 | ok | step | transition poll |
| 1653 | ok | perception_retry |  |
| 1654 | ok | step | perception retry (fusion_agreement_low) |
| 1655 | ok | step | app=WhatsApp screenshot=True |
| 1656 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1657 | ok | step | fallback=pyobjc_ax |
| 1658 | ok | step | nodes=1 elapsed=0.00s |
| 1659 | ok | observation |  |
| 1660 | fail | perception_unsettled |  |
| 1661 | ok | post_observation |  |
| 1662 | ok | post_world_patch |  |
| 1663 | fail | transition_eval |  |
| 1664 | ok | transition_attribution |  |
| 1665 | fail | verification |  |
| 1666 | ok | step | app=WhatsApp screenshot=True |
| 1667 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1668 | ok | step | fallback=pyobjc_ax |
| 1669 | ok | step | nodes=1 elapsed=0.00s |
| 1670 | ok | observation |  |
| 1671 | ok | post_transition_richer_reobserve |  |
| 1672 | fail | forward_predicate_rollback |  |
| 1673 | ok | step | app=WhatsApp screenshot=True |
| 1674 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1675 | ok | step | fallback=pyobjc_ax |
| 1676 | ok | step | nodes=1 elapsed=0.00s |
| 1677 | ok | observation |  |
| 1678 | ok | observation |  |
| 1679 | ok | forward_task |  |
| 1680 | ok | world_patch | dialog |
| 1681 | ok | goal_status |  |
| 1682 | ok | decision_engine |  |
| 1683 | ok | planner_decision |  |
| 1684 | ok | step | re-perceive current world (actuation/world uncertainty) |
| 1685 | ok | step | app=WhatsApp screenshot=True |
| 1686 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1687 | ok | step | fallback=pyobjc_ax |
| 1688 | ok | step | nodes=1 elapsed=0.01s |
| 1689 | ok | observation |  |
| 1690 | ok | observation |  |
| 1691 | ok | forward_task |  |
| 1692 | ok | world_patch | dialog |
| 1693 | ok | goal_status |  |
| 1694 | ok | decision_engine |  |
| 1695 | ok | planner_decision |  |
| 1696 | ok | step | re-perceive current world (actuation/world uncertainty) |
| 1697 | ok | step | app=WhatsApp screenshot=True |
| 1698 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1699 | ok | step | fallback=pyobjc_ax |
| 1700 | ok | step | nodes=1 elapsed=0.00s |
| 1701 | ok | observation |  |
| 1702 | ok | observation |  |
| 1703 | ok | forward_task |  |
| 1704 | ok | world_patch | dialog |
| 1705 | ok | goal_status |  |
| 1706 | ok | decision_engine |  |
| 1707 | ok | planner_decision |  |
| 1708 | ok | execution | pressed Escape |
| 1709 | ok | step | transition settle |
| 1710 | ok | step | app=WhatsApp screenshot=True |
| 1711 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1712 | ok | step | fallback=pyobjc_ax |
| 1713 | ok | step | nodes=1 elapsed=0.00s |
| 1714 | ok | observation |  |
| 1715 | ok | step | transition poll |
| 1716 | ok | step | app=WhatsApp screenshot=True |
| 1717 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1718 | ok | step | fallback=pyobjc_ax |
| 1719 | ok | step | nodes=1 elapsed=0.00s |
| 1720 | ok | observation |  |
| 1721 | ok | step | transition poll |
| 1722 | ok | step | app=WhatsApp screenshot=True |
| 1723 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1724 | ok | step | fallback=pyobjc_ax |
| 1725 | ok | step | nodes=1 elapsed=0.00s |
| 1726 | ok | observation |  |
| 1727 | ok | step | transition poll |
| 1728 | ok | perception_retry |  |
| 1729 | ok | step | perception retry (fusion_agreement_low) |
| 1730 | ok | step | app=WhatsApp screenshot=True |
| 1731 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1732 | ok | step | fallback=pyobjc_ax |
| 1733 | ok | step | nodes=1 elapsed=0.00s |
| 1734 | ok | observation |  |
| 1735 | fail | perception_unsettled |  |
| 1736 | ok | post_observation |  |
| 1737 | ok | post_world_patch |  |
| 1738 | fail | transition_eval |  |
| 1739 | ok | transition_attribution |  |
| 1740 | fail | verification |  |
| 1741 | ok | step | app=WhatsApp screenshot=True |
| 1742 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1743 | ok | step | fallback=pyobjc_ax |
| 1744 | ok | step | nodes=1 elapsed=0.00s |
| 1745 | ok | observation |  |
| 1746 | ok | post_transition_richer_reobserve |  |
| 1747 | fail | forward_predicate_rollback |  |
| 1748 | ok | step | app=WhatsApp screenshot=True |
| 1749 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1750 | ok | step | fallback=pyobjc_ax |
| 1751 | ok | step | nodes=1 elapsed=0.00s |
| 1752 | ok | observation |  |
| 1753 | ok | observation |  |
| 1754 | ok | forward_task |  |
| 1755 | ok | world_patch | dialog |
| 1756 | ok | goal_status |  |
| 1757 | ok | decision_engine |  |
| 1758 | ok | planner_decision |  |
| 1759 | ok | step | re-perceive current world (actuation/world uncertainty) |
| 1760 | ok | step | app=WhatsApp screenshot=True |
| 1761 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1762 | ok | step | fallback=pyobjc_ax |
| 1763 | ok | step | nodes=1 elapsed=0.00s |
| 1764 | ok | observation |  |
| 1765 | ok | observation |  |
| 1766 | ok | forward_task |  |
| 1767 | ok | world_patch | dialog |
| 1768 | ok | goal_status |  |
| 1769 | ok | decision_engine |  |
| 1770 | ok | planner_decision |  |
| 1771 | ok | step | re-perceive current world (actuation/world uncertainty) |
| 1772 | ok | step | app=WhatsApp screenshot=True |
| 1773 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1774 | ok | step | fallback=pyobjc_ax |
| 1775 | ok | step | nodes=1 elapsed=0.00s |
| 1776 | ok | observation |  |
| 1777 | ok | observation |  |
| 1778 | ok | forward_task |  |
| 1779 | ok | world_patch | dialog |
| 1780 | ok | goal_status |  |
| 1781 | ok | decision_engine |  |
| 1782 | ok | planner_decision |  |
| 1783 | ok | execution | pressed Escape |
| 1784 | ok | step | transition settle |
| 1785 | ok | step | app=WhatsApp screenshot=True |
| 1786 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1787 | ok | step | fallback=pyobjc_ax |
| 1788 | ok | step | nodes=1 elapsed=0.00s |
| 1789 | ok | observation |  |
| 1790 | ok | step | transition poll |
| 1791 | ok | step | app=WhatsApp screenshot=True |
| 1792 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1793 | ok | step | fallback=pyobjc_ax |
| 1794 | ok | step | nodes=1 elapsed=0.00s |
| 1795 | ok | observation |  |
| 1796 | ok | step | transition poll |
| 1797 | ok | step | app=WhatsApp screenshot=True |
| 1798 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1799 | ok | step | fallback=pyobjc_ax |
| 1800 | ok | step | nodes=1 elapsed=0.00s |
| 1801 | ok | observation |  |
| 1802 | ok | step | transition poll |
| 1803 | ok | step | app=WhatsApp screenshot=True |
| 1804 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1805 | ok | step | fallback=pyobjc_ax |
| 1806 | ok | step | nodes=1 elapsed=0.00s |
| 1807 | ok | observation |  |
| 1808 | ok | step | transition poll |
| 1809 | ok | perception_retry |  |
| 1810 | ok | step | perception retry (fusion_agreement_low) |
| 1811 | ok | step | app=WhatsApp screenshot=True |
| 1812 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1813 | ok | step | fallback=pyobjc_ax |
| 1814 | ok | step | nodes=1 elapsed=0.00s |
| 1815 | ok | observation |  |
| 1816 | fail | perception_unsettled |  |
| 1817 | ok | post_observation |  |
| 1818 | ok | post_world_patch |  |
| 1819 | fail | transition_eval |  |
| 1820 | ok | transition_attribution |  |
| 1821 | fail | verification |  |
| 1822 | ok | step | app=WhatsApp screenshot=True |
| 1823 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1824 | ok | step | fallback=pyobjc_ax |
| 1825 | ok | step | nodes=1 elapsed=0.00s |
| 1826 | ok | observation |  |
| 1827 | ok | post_transition_richer_reobserve |  |
| 1828 | fail | forward_predicate_rollback |  |
| 1829 | ok | step | app=WhatsApp screenshot=True |
| 1830 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1831 | ok | step | fallback=pyobjc_ax |
| 1832 | ok | step | nodes=1 elapsed=0.00s |
| 1833 | ok | observation |  |
| 1834 | ok | observation |  |
| 1835 | ok | forward_task |  |
| 1836 | ok | world_patch | dialog |
| 1837 | ok | goal_status |  |
| 1838 | ok | decision_engine |  |
| 1839 | ok | planner_decision |  |
| 1840 | ok | step | re-perceive current world (actuation/world uncertainty) |
| 1841 | ok | step | app=WhatsApp screenshot=True |
| 1842 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1843 | ok | step | fallback=pyobjc_ax |
| 1844 | ok | step | nodes=1 elapsed=0.00s |
| 1845 | ok | observation |  |
| 1846 | ok | observation |  |
| 1847 | ok | forward_task |  |
| 1848 | ok | world_patch | dialog |
| 1849 | ok | goal_status |  |
| 1850 | ok | decision_engine |  |
| 1851 | ok | planner_decision |  |
| 1852 | ok | step | re-perceive current world (actuation/world uncertainty) |
| 1853 | ok | step | app=WhatsApp screenshot=True |
| 1854 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1855 | ok | step | fallback=pyobjc_ax |
| 1856 | ok | step | nodes=1 elapsed=0.00s |
| 1857 | ok | observation |  |
| 1858 | ok | observation |  |
| 1859 | ok | forward_task |  |
| 1860 | ok | world_patch | dialog |
| 1861 | ok | goal_status |  |
| 1862 | ok | decision_engine |  |
| 1863 | ok | planner_decision |  |
| 1864 | ok | execution | pressed Escape |
| 1865 | ok | step | transition settle |
| 1866 | ok | step | app=WhatsApp screenshot=True |
| 1867 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1868 | ok | step | fallback=pyobjc_ax |
| 1869 | ok | step | nodes=1 elapsed=0.00s |
| 1870 | ok | observation |  |
| 1871 | ok | step | transition poll |
| 1872 | ok | step | app=WhatsApp screenshot=True |
| 1873 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1874 | ok | step | fallback=pyobjc_ax |
| 1875 | ok | step | nodes=1 elapsed=0.00s |
| 1876 | ok | observation |  |
| 1877 | ok | step | transition poll |
| 1878 | ok | step | app=WhatsApp screenshot=True |
| 1879 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1880 | ok | step | fallback=pyobjc_ax |
| 1881 | ok | step | nodes=1 elapsed=0.00s |
| 1882 | ok | observation |  |
| 1883 | ok | step | transition poll |
| 1884 | ok | perception_retry |  |
| 1885 | ok | step | perception retry (fusion_agreement_low) |
| 1886 | ok | step | app=WhatsApp screenshot=True |
| 1887 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1888 | ok | step | fallback=pyobjc_ax |
| 1889 | ok | step | nodes=1 elapsed=0.00s |
| 1890 | ok | observation |  |
| 1891 | fail | perception_unsettled |  |
| 1892 | ok | post_observation |  |
| 1893 | ok | post_world_patch |  |
| 1894 | fail | transition_eval |  |
| 1895 | ok | transition_attribution |  |
| 1896 | fail | verification |  |
| 1897 | ok | step | app=WhatsApp screenshot=True |
| 1898 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1899 | ok | step | fallback=pyobjc_ax |
| 1900 | ok | step | nodes=1 elapsed=0.00s |
| 1901 | ok | observation |  |
| 1902 | ok | post_transition_richer_reobserve |  |
| 1903 | fail | forward_predicate_rollback |  |
| 1904 | ok | step | app=WhatsApp screenshot=True |
| 1905 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1906 | ok | step | fallback=pyobjc_ax |
| 1907 | ok | step | nodes=1 elapsed=0.00s |
| 1908 | ok | observation |  |
| 1909 | ok | observation |  |
| 1910 | ok | forward_task |  |
| 1911 | ok | world_patch | dialog |
| 1912 | ok | goal_status |  |
| 1913 | ok | decision_engine |  |
| 1914 | ok | planner_decision |  |
| 1915 | ok | step | re-perceive current world (actuation/world uncertainty) |
| 1916 | ok | step | app=WhatsApp screenshot=True |
| 1917 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1918 | ok | step | fallback=pyobjc_ax |
| 1919 | ok | step | nodes=1 elapsed=0.00s |
| 1920 | ok | observation |  |
| 1921 | ok | observation |  |
| 1922 | ok | forward_task |  |
| 1923 | ok | world_patch | dialog |
| 1924 | ok | goal_status |  |
| 1925 | ok | decision_engine |  |
| 1926 | ok | planner_decision |  |
| 1927 | ok | step | re-perceive current world (actuation/world uncertainty) |
| 1928 | ok | step | app=WhatsApp screenshot=True |
| 1929 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1930 | ok | step | fallback=pyobjc_ax |
| 1931 | ok | step | nodes=1 elapsed=0.00s |
| 1932 | ok | observation |  |
| 1933 | ok | observation |  |
| 1934 | ok | forward_task |  |
| 1935 | ok | world_patch | dialog |
| 1936 | ok | goal_status |  |
| 1937 | ok | decision_engine |  |
| 1938 | ok | planner_decision |  |
| 1939 | ok | execution | pressed Escape |
| 1940 | ok | step | transition settle |
| 1941 | ok | step | app=WhatsApp screenshot=True |
| 1942 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1943 | ok | step | fallback=pyobjc_ax |
| 1944 | ok | step | nodes=1 elapsed=0.00s |
| 1945 | ok | observation |  |
| 1946 | ok | step | transition poll |
| 1947 | ok | step | app=WhatsApp screenshot=True |
| 1948 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1949 | ok | step | fallback=pyobjc_ax |
| 1950 | ok | step | nodes=1 elapsed=0.00s |
| 1951 | ok | observation |  |
| 1952 | ok | step | transition poll |
| 1953 | ok | step | app=WhatsApp screenshot=True |
| 1954 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1955 | ok | step | fallback=pyobjc_ax |
| 1956 | ok | step | nodes=1 elapsed=0.00s |
| 1957 | ok | observation |  |
| 1958 | ok | step | transition poll |
| 1959 | ok | perception_retry |  |
| 1960 | ok | step | perception retry (fusion_agreement_low) |
| 1961 | ok | step | app=WhatsApp screenshot=True |
| 1962 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1963 | ok | step | fallback=pyobjc_ax |
| 1964 | ok | step | nodes=1 elapsed=0.00s |
| 1965 | ok | observation |  |
| 1966 | fail | perception_unsettled |  |
| 1967 | ok | post_observation |  |
| 1968 | ok | post_world_patch |  |
| 1969 | fail | transition_eval |  |
| 1970 | ok | transition_attribution |  |
| 1971 | fail | verification |  |
| 1972 | ok | step | app=WhatsApp screenshot=True |
| 1973 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1974 | ok | step | fallback=pyobjc_ax |
| 1975 | ok | step | nodes=1 elapsed=0.00s |
| 1976 | ok | observation |  |
| 1977 | ok | post_transition_richer_reobserve |  |
| 1978 | fail | forward_predicate_rollback |  |
| 1979 | ok | step | app=WhatsApp screenshot=True |
| 1980 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1981 | ok | step | fallback=pyobjc_ax |
| 1982 | ok | step | nodes=1 elapsed=0.00s |
| 1983 | ok | observation |  |
| 1984 | ok | observation |  |
| 1985 | ok | forward_task |  |
| 1986 | ok | world_patch | dialog |
| 1987 | ok | goal_status |  |
| 1988 | ok | decision_engine |  |
| 1989 | ok | planner_decision |  |
| 1990 | ok | step | re-perceive current world (actuation/world uncertainty) |
| 1991 | ok | step | app=WhatsApp screenshot=True |
| 1992 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1993 | ok | step | fallback=pyobjc_ax |
| 1994 | ok | step | nodes=1 elapsed=0.00s |
| 1995 | ok | observation |  |
| 1996 | ok | observation |  |
| 1997 | ok | forward_task |  |
| 1998 | ok | world_patch | dialog |
| 1999 | ok | goal_status |  |
| 2000 | ok | decision_engine |  |
| 2001 | ok | planner_decision |  |
| 2002 | ok | step | re-perceive current world (actuation/world uncertainty) |
| 2003 | ok | step | app=WhatsApp screenshot=True |
| 2004 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 2005 | ok | step | fallback=pyobjc_ax |
| 2006 | ok | step | nodes=1 elapsed=0.00s |
| 2007 | ok | observation |  |
| 2008 | ok | observation |  |
| 2009 | ok | forward_task |  |
| 2010 | ok | world_patch | dialog |
| 2011 | ok | goal_status |  |
| 2012 | ok | decision_engine |  |
| 2013 | ok | planner_decision |  |
| 2014 | ok | execution | pressed Escape |
| 2015 | ok | step | transition settle |
| 2016 | ok | step | app=WhatsApp screenshot=True |
| 2017 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 2018 | ok | step | fallback=pyobjc_ax |
| 2019 | ok | step | nodes=1 elapsed=0.00s |
| 2020 | ok | observation |  |
| 2021 | ok | step | transition poll |
| 2022 | ok | step | app=WhatsApp screenshot=True |
| 2023 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 2024 | ok | step | fallback=pyobjc_ax |
| 2025 | ok | step | nodes=1 elapsed=0.00s |
| 2026 | ok | observation |  |
| 2027 | ok | step | transition poll |
| 2028 | ok | step | app=WhatsApp screenshot=True |
| 2029 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 2030 | ok | step | fallback=pyobjc_ax |
| 2031 | ok | step | nodes=1 elapsed=0.00s |
| 2032 | ok | observation |  |
| 2033 | ok | step | transition poll |
| 2034 | ok | step | app=WhatsApp screenshot=True |
| 2035 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 2036 | ok | step | fallback=pyobjc_ax |
| 2037 | ok | step | nodes=1 elapsed=0.00s |
| 2038 | ok | observation |  |
| 2039 | ok | step | transition poll |
| 2040 | ok | perception_retry |  |
| 2041 | ok | step | perception retry (fusion_agreement_low) |
| 2042 | ok | step | app=WhatsApp screenshot=True |
| 2043 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 2044 | ok | step | fallback=pyobjc_ax |
| 2045 | ok | step | nodes=1 elapsed=0.00s |
| 2046 | ok | observation |  |
| 2047 | fail | perception_unsettled |  |
| 2048 | ok | post_observation |  |
| 2049 | ok | post_world_patch |  |
| 2050 | fail | transition_eval |  |
| 2051 | ok | transition_attribution |  |
| 2052 | fail | verification |  |
| 2053 | ok | step | app=WhatsApp screenshot=True |
| 2054 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 2055 | ok | step | fallback=pyobjc_ax |
| 2056 | ok | step | nodes=1 elapsed=0.00s |
| 2057 | ok | observation |  |
| 2058 | ok | post_transition_richer_reobserve |  |
| 2059 | fail | forward_predicate_rollback |  |
| 2060 | ok | step | app=WhatsApp screenshot=True |
| 2061 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 2062 | ok | step | fallback=pyobjc_ax |
| 2063 | ok | step | nodes=1 elapsed=0.00s |
| 2064 | ok | observation |  |
| 2065 | ok | observation |  |
| 2066 | ok | forward_task |  |
| 2067 | ok | world_patch | dialog |
| 2068 | ok | goal_status |  |
| 2069 | ok | decision_engine |  |
| 2070 | ok | planner_decision |  |
| 2071 | ok | step | re-perceive current world (actuation/world uncertainty) |
| 2072 | ok | step | app=WhatsApp screenshot=True |
| 2073 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 2074 | ok | step | fallback=pyobjc_ax |
| 2075 | ok | step | nodes=1 elapsed=0.00s |
| 2076 | ok | observation |  |
| 2077 | ok | observation |  |
| 2078 | ok | forward_task |  |
| 2079 | ok | world_patch | dialog |
| 2080 | ok | goal_status |  |
| 2081 | ok | decision_engine |  |
| 2082 | ok | planner_decision |  |
| 2083 | ok | step | re-perceive current world (actuation/world uncertainty) |
| 2084 | ok | step | app=WhatsApp screenshot=True |
| 2085 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 2086 | ok | step | fallback=pyobjc_ax |
| 2087 | ok | step | nodes=1 elapsed=0.00s |
| 2088 | ok | observation |  |
| 2089 | ok | observation |  |
| 2090 | ok | forward_task |  |
| 2091 | ok | world_patch | dialog |
| 2092 | ok | goal_status |  |
| 2093 | ok | decision_engine |  |
| 2094 | ok | planner_decision |  |
| 2095 | ok | execution | pressed Escape |
| 2096 | ok | step | transition settle |
| 2097 | ok | step | app=WhatsApp screenshot=True |
| 2098 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 2099 | ok | step | fallback=pyobjc_ax |
| 2100 | ok | step | nodes=1 elapsed=0.00s |
| 2101 | ok | observation |  |
| 2102 | ok | step | transition poll |
| 2103 | ok | step | app=WhatsApp screenshot=True |
| 2104 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 2105 | ok | step | fallback=pyobjc_ax |
| 2106 | ok | step | nodes=1 elapsed=0.00s |
| 2107 | ok | observation |  |
| 2108 | ok | step | transition poll |
| 2109 | ok | step | app=WhatsApp screenshot=True |
| 2110 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 2111 | ok | step | fallback=pyobjc_ax |
| 2112 | ok | step | nodes=1 elapsed=0.00s |
| 2113 | ok | observation |  |
| 2114 | ok | step | transition poll |
| 2115 | ok | step | app=WhatsApp screenshot=True |
| 2116 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 2117 | ok | step | fallback=pyobjc_ax |
| 2118 | ok | step | nodes=1 elapsed=0.00s |
| 2119 | ok | observation |  |
| 2120 | ok | step | transition poll |
| 2121 | ok | perception_retry |  |
| 2122 | ok | step | perception retry (fusion_agreement_low) |
| 2123 | ok | step | app=WhatsApp screenshot=True |
| 2124 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 2125 | ok | step | fallback=pyobjc_ax |
| 2126 | ok | step | nodes=1 elapsed=0.00s |
| 2127 | ok | observation |  |
| 2128 | fail | perception_unsettled |  |
| 2129 | ok | post_observation |  |
| 2130 | ok | post_world_patch |  |
| 2131 | fail | transition_eval |  |
| 2132 | ok | transition_attribution |  |
| 2133 | fail | verification |  |
| 2134 | ok | step | app=WhatsApp screenshot=True |
| 2135 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 2136 | ok | step | fallback=pyobjc_ax |
| 2137 | ok | step | nodes=1 elapsed=0.00s |
| 2138 | ok | observation |  |
| 2139 | ok | post_transition_richer_reobserve |  |
| 2140 | fail | forward_predicate_rollback |  |
| 2141 | ok | step | app=WhatsApp screenshot=True |
| 2142 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 2143 | ok | step | fallback=pyobjc_ax |
| 2144 | ok | step | nodes=1 elapsed=0.00s |
| 2145 | ok | observation |  |
| 2146 | ok | observation |  |
| 2147 | ok | forward_task |  |
| 2148 | ok | world_patch | dialog |
| 2149 | ok | goal_status |  |
| 2150 | ok | decision_engine |  |
| 2151 | ok | planner_decision |  |
| 2152 | ok | step | re-perceive current world (actuation/world uncertainty) |
| 2153 | ok | step | app=WhatsApp screenshot=True |
| 2154 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 2155 | ok | step | fallback=pyobjc_ax |
| 2156 | ok | step | nodes=1 elapsed=0.00s |
| 2157 | ok | observation |  |
| 2158 | ok | observation |  |
| 2159 | ok | forward_task |  |
| 2160 | ok | world_patch | dialog |
| 2161 | ok | goal_status |  |
| 2162 | ok | decision_engine |  |
| 2163 | ok | planner_decision |  |
| 2164 | ok | step | re-perceive current world (actuation/world uncertainty) |
| 2165 | ok | step | app=WhatsApp screenshot=True |
| 2166 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 2167 | ok | step | fallback=pyobjc_ax |
| 2168 | ok | step | nodes=1 elapsed=0.00s |
| 2169 | ok | observation |  |
| 2170 | ok | observation |  |
| 2171 | ok | forward_task |  |
| 2172 | ok | world_patch | dialog |
| 2173 | ok | goal_status |  |
| 2174 | ok | decision_engine |  |
| 2175 | ok | planner_decision |  |
| 2176 | ok | execution | pressed Escape |
| 2177 | ok | step | transition settle |
| 2178 | ok | step | app=WhatsApp screenshot=True |
| 2179 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 2180 | ok | step | fallback=pyobjc_ax |
| 2181 | ok | step | nodes=1 elapsed=0.00s |
| 2182 | ok | observation |  |
| 2183 | ok | step | transition poll |
| 2184 | ok | step | app=WhatsApp screenshot=True |
| 2185 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 2186 | ok | step | fallback=pyobjc_ax |
| 2187 | ok | step | nodes=1 elapsed=0.00s |
| 2188 | ok | observation |  |
| 2189 | ok | step | transition poll |
| 2190 | ok | perception_retry |  |
| 2191 | ok | step | perception retry (fusion_agreement_low) |
| 2192 | ok | step | app=WhatsApp screenshot=True |
| 2193 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 2194 | ok | step | fallback=pyobjc_ax |
| 2195 | ok | step | nodes=1 elapsed=0.00s |
| 2196 | ok | observation |  |
| 2197 | fail | perception_unsettled |  |
| 2198 | ok | post_observation |  |
| 2199 | ok | post_world_patch |  |
| 2200 | fail | transition_eval |  |
| 2201 | ok | transition_attribution |  |
| 2202 | fail | verification |  |
| 2203 | ok | step | app=WhatsApp screenshot=True |
| 2204 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 2205 | ok | step | fallback=pyobjc_ax |
| 2206 | ok | step | nodes=1 elapsed=0.00s |
| 2207 | ok | observation |  |
| 2208 | ok | post_transition_richer_reobserve |  |
| 2209 | fail | forward_predicate_rollback |  |
| 2210 | ok | step | app=WhatsApp screenshot=True |
| 2211 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 2212 | ok | step | fallback=pyobjc_ax |
| 2213 | ok | step | nodes=1 elapsed=0.00s |
| 2214 | ok | observation |  |
| 2215 | ok | observation |  |
| 2216 | ok | forward_task |  |
| 2217 | ok | world_patch | dialog |
| 2218 | ok | goal_status |  |
| 2219 | ok | decision_engine |  |
| 2220 | ok | planner_decision |  |
| 2221 | ok | step | re-perceive current world (actuation/world uncertainty) |
| 2222 | ok | step | app=WhatsApp screenshot=True |
| 2223 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 2224 | ok | step | fallback=pyobjc_ax |
| 2225 | ok | step | nodes=1 elapsed=0.00s |
| 2226 | ok | observation |  |
| 2227 | ok | observation |  |
| 2228 | ok | forward_task |  |
| 2229 | ok | world_patch | dialog |
| 2230 | ok | goal_status |  |
| 2231 | ok | decision_engine |  |
| 2232 | ok | planner_decision |  |
| 2233 | ok | step | re-perceive current world (actuation/world uncertainty) |
| 2234 | ok | step | app=WhatsApp screenshot=True |
| 2235 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 2236 | ok | step | fallback=pyobjc_ax |
| 2237 | ok | step | nodes=1 elapsed=0.00s |
| 2238 | ok | observation |  |
| 2239 | ok | observation |  |
| 2240 | ok | forward_task |  |
| 2241 | ok | world_patch | dialog |
| 2242 | ok | goal_status |  |
| 2243 | ok | decision_engine |  |
| 2244 | ok | planner_decision |  |
| 2245 | ok | execution | pressed Escape |
| 2246 | ok | step | transition settle |
| 2247 | ok | step | app=WhatsApp screenshot=True |
| 2248 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 2249 | ok | step | fallback=pyobjc_ax |
| 2250 | ok | step | nodes=1 elapsed=0.00s |
| 2251 | ok | observation |  |
| 2252 | ok | step | transition poll |
| 2253 | ok | step | app=WhatsApp screenshot=True |
| 2254 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 2255 | ok | step | fallback=pyobjc_ax |
| 2256 | ok | step | nodes=1 elapsed=0.00s |
| 2257 | ok | observation |  |
| 2258 | ok | step | transition poll |
| 2259 | ok | step | app=WhatsApp screenshot=True |
| 2260 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 2261 | ok | step | fallback=pyobjc_ax |
| 2262 | ok | step | nodes=1 elapsed=0.00s |
| 2263 | ok | observation |  |
| 2264 | ok | step | transition poll |
| 2265 | ok | perception_retry |  |
| 2266 | ok | step | perception retry (fusion_agreement_low) |
| 2267 | ok | step | app=WhatsApp screenshot=True |
| 2268 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 2269 | ok | step | fallback=pyobjc_ax |
| 2270 | ok | step | nodes=1 elapsed=0.00s |
| 2271 | ok | observation |  |
| 2272 | fail | perception_unsettled |  |
| 2273 | ok | post_observation |  |
| 2274 | ok | post_world_patch |  |
| 2275 | fail | transition_eval |  |
| 2276 | ok | transition_attribution |  |
| 2277 | fail | verification |  |
| 2278 | ok | step | app=WhatsApp screenshot=True |
| 2279 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 2280 | ok | step | fallback=pyobjc_ax |
| 2281 | ok | step | nodes=1 elapsed=0.00s |
| 2282 | ok | observation |  |
| 2283 | ok | post_transition_richer_reobserve |  |
| 2284 | fail | forward_predicate_rollback |  |
| 2285 | ok | step | app=WhatsApp screenshot=True |
| 2286 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 2287 | ok | step | fallback=pyobjc_ax |
| 2288 | ok | step | nodes=1 elapsed=0.00s |
| 2289 | ok | observation |  |
| 2290 | ok | observation |  |
| 2291 | ok | forward_task |  |
| 2292 | ok | world_patch | dialog |
| 2293 | ok | goal_status |  |
| 2294 | ok | decision_engine |  |
| 2295 | ok | planner_decision |  |
| 2296 | ok | step | re-perceive current world (actuation/world uncertainty) |
| 2297 | ok | step | app=WhatsApp screenshot=True |
| 2298 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 2299 | ok | step | fallback=pyobjc_ax |
| 2300 | ok | step | nodes=1 elapsed=0.00s |
| 2301 | ok | observation |  |
| 2302 | ok | observation |  |
| 2303 | ok | forward_task |  |
| 2304 | ok | world_patch | dialog |
| 2305 | ok | goal_status |  |
| 2306 | ok | decision_engine |  |
| 2307 | ok | planner_decision |  |
| 2308 | ok | step | re-perceive current world (actuation/world uncertainty) |
| 2309 | ok | step | app=WhatsApp screenshot=True |
| 2310 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 2311 | ok | step | fallback=pyobjc_ax |
| 2312 | ok | step | nodes=1 elapsed=0.00s |
| 2313 | ok | observation |  |
| 2314 | ok | observation |  |
| 2315 | ok | forward_task |  |
| 2316 | ok | world_patch | dialog |
| 2317 | ok | goal_status |  |
| 2318 | ok | decision_engine |  |
| 2319 | ok | planner_decision |  |
| 2320 | ok | execution | pressed Escape |
| 2321 | ok | step | transition settle |
| 2322 | ok | step | app=WhatsApp screenshot=True |
| 2323 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 2324 | ok | step | fallback=pyobjc_ax |
| 2325 | ok | step | nodes=1 elapsed=0.00s |
| 2326 | ok | observation |  |
| 2327 | ok | step | transition poll |
| 2328 | ok | step | app=WhatsApp screenshot=True |
| 2329 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 2330 | ok | step | fallback=pyobjc_ax |
| 2331 | ok | step | nodes=1 elapsed=0.01s |
| 2332 | ok | observation |  |
| 2333 | ok | step | transition poll |
| 2334 | ok | perception_retry |  |
| 2335 | ok | step | perception retry (fusion_agreement_low) |
| 2336 | ok | step | app=WhatsApp screenshot=True |
| 2337 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 2338 | ok | step | fallback=pyobjc_ax |
| 2339 | ok | step | nodes=1 elapsed=0.00s |
| 2340 | ok | observation |  |
| 2341 | fail | perception_unsettled |  |
| 2342 | ok | post_observation |  |
| 2343 | ok | post_world_patch |  |
| 2344 | fail | transition_eval |  |
| 2345 | ok | transition_attribution |  |
| 2346 | fail | verification |  |
| 2347 | ok | step | app=WhatsApp screenshot=True |
| 2348 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 2349 | ok | step | fallback=pyobjc_ax |
| 2350 | ok | step | nodes=1 elapsed=0.00s |
| 2351 | ok | observation |  |
| 2352 | ok | post_transition_richer_reobserve |  |
| 2353 | fail | forward_predicate_rollback |  |
| 2354 | ok | step | app=WhatsApp screenshot=True |
| 2355 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 2356 | ok | step | fallback=pyobjc_ax |
| 2357 | ok | step | nodes=1 elapsed=0.00s |
| 2358 | ok | observation |  |
| 2359 | ok | observation |  |
| 2360 | ok | forward_task |  |
| 2361 | ok | world_patch | dialog |
| 2362 | ok | goal_status |  |
| 2363 | ok | decision_engine |  |
| 2364 | ok | planner_decision |  |
| 2365 | ok | step | re-perceive current world (actuation/world uncertainty) |
| 2366 | ok | step | app=WhatsApp screenshot=True |
| 2367 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 2368 | ok | step | fallback=pyobjc_ax |
| 2369 | ok | step | nodes=1 elapsed=0.00s |
| 2370 | ok | observation |  |
| 2371 | ok | observation |  |
| 2372 | ok | forward_task |  |
| 2373 | ok | world_patch | dialog |
| 2374 | ok | goal_status |  |
| 2375 | ok | decision_engine |  |
| 2376 | ok | planner_decision |  |
| 2377 | ok | step | re-perceive current world (actuation/world uncertainty) |
| 2378 | ok | step | app=WhatsApp screenshot=True |
| 2379 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 2380 | ok | step | fallback=pyobjc_ax |
| 2381 | ok | step | nodes=1 elapsed=0.00s |
| 2382 | ok | observation |  |
| 2383 | ok | observation |  |
| 2384 | ok | forward_task |  |
| 2385 | ok | world_patch | dialog |
| 2386 | ok | goal_status |  |
| 2387 | ok | decision_engine |  |
| 2388 | ok | planner_decision |  |
| 2389 | ok | execution | pressed Escape |
| 2390 | ok | step | transition settle |
| 2391 | ok | step | app=WhatsApp screenshot=True |
| 2392 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 2393 | ok | step | fallback=pyobjc_ax |
| 2394 | ok | step | nodes=1 elapsed=0.00s |
| 2395 | ok | observation |  |
| 2396 | ok | step | transition poll |
| 2397 | ok | step | app=WhatsApp screenshot=True |
| 2398 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 2399 | ok | step | fallback=pyobjc_ax |
| 2400 | ok | step | nodes=1 elapsed=0.00s |
| 2401 | ok | observation |  |
| 2402 | ok | step | transition poll |
| 2403 | ok | step | app=WhatsApp screenshot=True |
| 2404 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 2405 | ok | step | fallback=pyobjc_ax |
| 2406 | ok | step | nodes=1 elapsed=0.00s |
| 2407 | ok | observation |  |
| 2408 | ok | step | transition poll |
| 2409 | ok | perception_retry |  |
| 2410 | ok | step | perception retry (fusion_agreement_low) |
| 2411 | ok | step | app=WhatsApp screenshot=True |
| 2412 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 2413 | ok | step | fallback=pyobjc_ax |
| 2414 | ok | step | nodes=1 elapsed=0.00s |
| 2415 | ok | observation |  |
| 2416 | fail | perception_unsettled |  |
| 2417 | ok | post_observation |  |
| 2418 | ok | post_world_patch |  |
| 2419 | fail | transition_eval |  |
| 2420 | ok | transition_attribution |  |
| 2421 | fail | verification |  |
| 2422 | ok | step | app=WhatsApp screenshot=True |
| 2423 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 2424 | ok | step | fallback=pyobjc_ax |
| 2425 | ok | step | nodes=1 elapsed=0.00s |
| 2426 | ok | observation |  |
| 2427 | ok | post_transition_richer_reobserve |  |
| 2428 | fail | forward_predicate_rollback |  |
| 2429 | ok | step | app=WhatsApp screenshot=True |
| 2430 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 2431 | ok | step | fallback=pyobjc_ax |
| 2432 | ok | step | nodes=1 elapsed=0.00s |
| 2433 | ok | observation |  |
| 2434 | ok | observation |  |
| 2435 | ok | forward_task |  |
| 2436 | ok | world_patch | dialog |
| 2437 | ok | goal_status |  |
| 2438 | ok | decision_engine |  |
| 2439 | ok | planner_decision |  |
| 2440 | ok | step | re-perceive current world (actuation/world uncertainty) |
| 2441 | ok | step | app=WhatsApp screenshot=True |
| 2442 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 2443 | ok | step | fallback=pyobjc_ax |
| 2444 | ok | step | nodes=1 elapsed=0.00s |
| 2445 | ok | observation |  |
| 2446 | ok | observation |  |
| 2447 | ok | forward_task |  |
| 2448 | ok | world_patch | dialog |
| 2449 | ok | goal_status |  |
| 2450 | ok | decision_engine |  |
| 2451 | ok | planner_decision |  |
| 2452 | ok | step | re-perceive current world (actuation/world uncertainty) |
| 2453 | ok | step | app=WhatsApp screenshot=True |
| 2454 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 2455 | ok | step | fallback=pyobjc_ax |
| 2456 | ok | step | nodes=1 elapsed=0.00s |
| 2457 | ok | observation |  |
| 2458 | ok | observation |  |
| 2459 | ok | forward_task |  |
| 2460 | ok | world_patch | dialog |
| 2461 | ok | goal_status |  |
| 2462 | ok | decision_engine |  |
| 2463 | ok | planner_decision |  |
| 2464 | ok | execution | pressed Escape |
| 2465 | ok | step | transition settle |
| 2466 | ok | step | app=WhatsApp screenshot=True |
| 2467 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 2468 | ok | step | fallback=pyobjc_ax |
| 2469 | ok | step | nodes=1 elapsed=0.00s |
| 2470 | ok | observation |  |
| 2471 | ok | step | transition poll |
| 2472 | ok | step | app=WhatsApp screenshot=True |
| 2473 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 2474 | ok | step | fallback=pyobjc_ax |
| 2475 | ok | step | nodes=1 elapsed=0.00s |
| 2476 | ok | observation |  |
| 2477 | ok | step | transition poll |
| 2478 | ok | step | app=WhatsApp screenshot=True |
| 2479 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 2480 | ok | step | fallback=pyobjc_ax |
| 2481 | ok | step | nodes=1 elapsed=0.00s |
| 2482 | ok | observation |  |
| 2483 | ok | step | transition poll |
| 2484 | ok | perception_retry |  |
| 2485 | ok | step | perception retry (fusion_agreement_low) |
| 2486 | ok | step | app=WhatsApp screenshot=True |
| 2487 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 2488 | ok | step | fallback=pyobjc_ax |
| 2489 | ok | step | nodes=1 elapsed=0.00s |
| 2490 | ok | observation |  |
| 2491 | fail | perception_unsettled |  |
| 2492 | ok | post_observation |  |
| 2493 | ok | post_world_patch |  |
| 2494 | fail | transition_eval |  |
| 2495 | ok | transition_attribution |  |
| 2496 | fail | verification |  |
| 2497 | ok | step | app=WhatsApp screenshot=True |
| 2498 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 2499 | ok | step | fallback=pyobjc_ax |
| 2500 | ok | step | nodes=1 elapsed=0.00s |
| 2501 | ok | observation |  |
| 2502 | ok | post_transition_richer_reobserve |  |
| 2503 | fail | forward_predicate_rollback |  |
| 2504 | ok | step | app=WhatsApp screenshot=True |
| 2505 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 2506 | ok | step | fallback=pyobjc_ax |
| 2507 | ok | step | nodes=1 elapsed=0.00s |
| 2508 | ok | observation |  |
| 2509 | ok | observation |  |
| 2510 | ok | forward_task |  |
| 2511 | ok | world_patch | dialog |
| 2512 | ok | goal_status |  |
| 2513 | ok | decision_engine |  |
| 2514 | ok | planner_decision |  |
| 2515 | ok | step | re-perceive current world (actuation/world uncertainty) |
| 2516 | ok | step | app=WhatsApp screenshot=True |
| 2517 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 2518 | ok | step | fallback=pyobjc_ax |
| 2519 | ok | step | nodes=1 elapsed=0.00s |
| 2520 | ok | observation |  |
| 2521 | ok | observation |  |
| 2522 | ok | forward_task |  |
| 2523 | ok | world_patch | dialog |
| 2524 | ok | goal_status |  |
| 2525 | ok | decision_engine |  |
| 2526 | ok | planner_decision |  |
| 2527 | ok | step | re-perceive current world (actuation/world uncertainty) |
| 2528 | ok | world_summary |  |
| 2529 | fail | check | fail |
| 2530 | fail | run_end | closed_loop ok=False reason='Maximum step count reached' iterations=99 |

## Failures

- seq=5 `check`: {"ts": 1785219745.4869199, "seq": 5, "run_id": "wa-forward-live-1785219745", "kind": "check", "status": "fail", "name": "ghost_cli_installed", "expected": true, "actual": false, "message": "fail", "st
- seq=72 `perception_unsettled`: {"ts": 1785219798.477837, "seq": 72, "run_id": "wa-forward-live-1785219745", "kind": "perception_unsettled", "status": "fail", "settled": false, "failure_modes": ["fusion_agreement_low"], "retry_strat
- seq=75 `transition_eval`: {"ts": 1785219798.49565, "seq": 75, "run_id": "wa-forward-live-1785219745", "kind": "transition_eval", "status": "fail", "attempt": {"before_world_id": "w0", "after_world_id": "w0", "action_family": "
- seq=77 `verification`: {"ts": 1785219798.496114, "seq": 77, "run_id": "wa-forward-live-1785219745", "kind": "verification", "status": "fail", "passed": false, "reason": "no_effect", "expected_predicate": "TransitionEvaluato
- seq=83 `forward_predicate_rollback`: {"ts": 1785219799.339104, "seq": 83, "run_id": "wa-forward-live-1785219745", "kind": "forward_predicate_rollback", "status": "fail", "expected": "NoUnexpectedDialog", "outcome": "no_effect", "forward_
- seq=134 `perception_unsettled`: {"ts": 1785219818.264179, "seq": 134, "run_id": "wa-forward-live-1785219745", "kind": "perception_unsettled", "status": "fail", "settled": false, "failure_modes": ["fusion_agreement_low"], "retry_stra
- seq=137 `transition_eval`: {"ts": 1785219818.2970948, "seq": 137, "run_id": "wa-forward-live-1785219745", "kind": "transition_eval", "status": "fail", "attempt": {"before_world_id": "w0", "after_world_id": "w0", "action_family"
- seq=139 `verification`: {"ts": 1785219818.2979279, "seq": 139, "run_id": "wa-forward-live-1785219745", "kind": "verification", "status": "fail", "passed": false, "reason": "no_effect", "expected_predicate": "TransitionEvalua
- seq=145 `forward_predicate_rollback`: {"ts": 1785219819.745398, "seq": 145, "run_id": "wa-forward-live-1785219745", "kind": "forward_predicate_rollback", "status": "fail", "expected": "NoUnexpectedDialog", "outcome": "no_effect", "forward
- seq=205 `perception_unsettled`: {"ts": 1785219842.444865, "seq": 205, "run_id": "wa-forward-live-1785219745", "kind": "perception_unsettled", "status": "fail", "settled": false, "failure_modes": ["fusion_agreement_low"], "retry_stra
- seq=208 `transition_eval`: {"ts": 1785219842.4740632, "seq": 208, "run_id": "wa-forward-live-1785219745", "kind": "transition_eval", "status": "fail", "attempt": {"before_world_id": "w0", "after_world_id": "w0", "action_family"
- seq=210 `verification`: {"ts": 1785219842.4745018, "seq": 210, "run_id": "wa-forward-live-1785219745", "kind": "verification", "status": "fail", "passed": false, "reason": "no_effect", "expected_predicate": "TransitionEvalua
- seq=217 `forward_predicate_rollback`: {"ts": 1785219842.7074711, "seq": 217, "run_id": "wa-forward-live-1785219745", "kind": "forward_predicate_rollback", "status": "fail", "expected": "NoUnexpectedDialog", "outcome": "no_effect", "forwar
- seq=280 `perception_unsettled`: {"ts": 1785219859.944788, "seq": 280, "run_id": "wa-forward-live-1785219745", "kind": "perception_unsettled", "status": "fail", "settled": false, "failure_modes": ["fusion_agreement_low"], "retry_stra
- seq=283 `transition_eval`: {"ts": 1785219859.9711192, "seq": 283, "run_id": "wa-forward-live-1785219745", "kind": "transition_eval", "status": "fail", "attempt": {"before_world_id": "w0", "after_world_id": "w0", "action_family"
- seq=285 `verification`: {"ts": 1785219859.971906, "seq": 285, "run_id": "wa-forward-live-1785219745", "kind": "verification", "status": "fail", "passed": false, "reason": "no_effect", "expected_predicate": "TransitionEvaluat
- seq=292 `forward_predicate_rollback`: {"ts": 1785219860.157349, "seq": 292, "run_id": "wa-forward-live-1785219745", "kind": "forward_predicate_rollback", "status": "fail", "expected": "NoUnexpectedDialog", "outcome": "no_effect", "forward
- seq=355 `perception_unsettled`: {"ts": 1785219880.670814, "seq": 355, "run_id": "wa-forward-live-1785219745", "kind": "perception_unsettled", "status": "fail", "settled": false, "failure_modes": ["fusion_agreement_low"], "retry_stra
- seq=358 `transition_eval`: {"ts": 1785219880.709884, "seq": 358, "run_id": "wa-forward-live-1785219745", "kind": "transition_eval", "status": "fail", "attempt": {"before_world_id": "w0", "after_world_id": "w0", "action_family":
- seq=360 `verification`: {"ts": 1785219880.7107809, "seq": 360, "run_id": "wa-forward-live-1785219745", "kind": "verification", "status": "fail", "passed": false, "reason": "no_effect", "expected_predicate": "TransitionEvalua
- seq=367 `forward_predicate_rollback`: {"ts": 1785219881.006797, "seq": 367, "run_id": "wa-forward-live-1785219745", "kind": "forward_predicate_rollback", "status": "fail", "expected": "NoUnexpectedDialog", "outcome": "no_effect", "forward
- seq=436 `perception_unsettled`: {"ts": 1785219897.589817, "seq": 436, "run_id": "wa-forward-live-1785219745", "kind": "perception_unsettled", "status": "fail", "settled": false, "failure_modes": ["fusion_agreement_low"], "retry_stra
- seq=439 `transition_eval`: {"ts": 1785219897.610187, "seq": 439, "run_id": "wa-forward-live-1785219745", "kind": "transition_eval", "status": "fail", "attempt": {"before_world_id": "w0", "after_world_id": "w0", "action_family":
- seq=441 `verification`: {"ts": 1785219897.610573, "seq": 441, "run_id": "wa-forward-live-1785219745", "kind": "verification", "status": "fail", "passed": false, "reason": "no_effect", "expected_predicate": "TransitionEvaluat
- seq=448 `forward_predicate_rollback`: {"ts": 1785219897.7831528, "seq": 448, "run_id": "wa-forward-live-1785219745", "kind": "forward_predicate_rollback", "status": "fail", "expected": "NoUnexpectedDialog", "outcome": "no_effect", "forwar
- seq=511 `perception_unsettled`: {"ts": 1785219916.449065, "seq": 511, "run_id": "wa-forward-live-1785219745", "kind": "perception_unsettled", "status": "fail", "settled": false, "failure_modes": ["fusion_agreement_low"], "retry_stra
- seq=514 `transition_eval`: {"ts": 1785219916.4726348, "seq": 514, "run_id": "wa-forward-live-1785219745", "kind": "transition_eval", "status": "fail", "attempt": {"before_world_id": "w0", "after_world_id": "w0", "action_family"
- seq=516 `verification`: {"ts": 1785219916.4731221, "seq": 516, "run_id": "wa-forward-live-1785219745", "kind": "verification", "status": "fail", "passed": false, "reason": "no_effect", "expected_predicate": "TransitionEvalua
- seq=523 `forward_predicate_rollback`: {"ts": 1785219916.8198102, "seq": 523, "run_id": "wa-forward-live-1785219745", "kind": "forward_predicate_rollback", "status": "fail", "expected": "NoUnexpectedDialog", "outcome": "no_effect", "forwar
- seq=580 `perception_unsettled`: {"ts": 1785219941.577139, "seq": 580, "run_id": "wa-forward-live-1785219745", "kind": "perception_unsettled", "status": "fail", "settled": false, "failure_modes": ["fusion_agreement_low"], "retry_stra
- seq=583 `transition_eval`: {"ts": 1785219941.611064, "seq": 583, "run_id": "wa-forward-live-1785219745", "kind": "transition_eval", "status": "fail", "attempt": {"before_world_id": "w0", "after_world_id": "w0", "action_family":
- seq=585 `verification`: {"ts": 1785219941.6115751, "seq": 585, "run_id": "wa-forward-live-1785219745", "kind": "verification", "status": "fail", "passed": false, "reason": "no_effect", "expected_predicate": "TransitionEvalua
- seq=592 `forward_predicate_rollback`: {"ts": 1785219941.933538, "seq": 592, "run_id": "wa-forward-live-1785219745", "kind": "forward_predicate_rollback", "status": "fail", "expected": "NoUnexpectedDialog", "outcome": "no_effect", "forward
- seq=661 `perception_unsettled`: {"ts": 1785219954.198693, "seq": 661, "run_id": "wa-forward-live-1785219745", "kind": "perception_unsettled", "status": "fail", "settled": false, "failure_modes": ["fusion_agreement_low"], "retry_stra
- seq=664 `transition_eval`: {"ts": 1785219954.215051, "seq": 664, "run_id": "wa-forward-live-1785219745", "kind": "transition_eval", "status": "fail", "attempt": {"before_world_id": "w0", "after_world_id": "w0", "action_family":
- seq=666 `verification`: {"ts": 1785219954.215335, "seq": 666, "run_id": "wa-forward-live-1785219745", "kind": "verification", "status": "fail", "passed": false, "reason": "no_effect", "expected_predicate": "TransitionEvaluat
- seq=673 `forward_predicate_rollback`: {"ts": 1785219954.332719, "seq": 673, "run_id": "wa-forward-live-1785219745", "kind": "forward_predicate_rollback", "status": "fail", "expected": "NoUnexpectedDialog", "outcome": "no_effect", "forward
- seq=736 `perception_unsettled`: {"ts": 1785219969.0719638, "seq": 736, "run_id": "wa-forward-live-1785219745", "kind": "perception_unsettled", "status": "fail", "settled": false, "failure_modes": ["fusion_agreement_low"], "retry_str
- seq=739 `transition_eval`: {"ts": 1785219969.0893362, "seq": 739, "run_id": "wa-forward-live-1785219745", "kind": "transition_eval", "status": "fail", "attempt": {"before_world_id": "w0", "after_world_id": "w0", "action_family"
- seq=741 `verification`: {"ts": 1785219969.089769, "seq": 741, "run_id": "wa-forward-live-1785219745", "kind": "verification", "status": "fail", "passed": false, "reason": "no_effect", "expected_predicate": "TransitionEvaluat
- seq=748 `forward_predicate_rollback`: {"ts": 1785219969.205188, "seq": 748, "run_id": "wa-forward-live-1785219745", "kind": "forward_predicate_rollback", "status": "fail", "expected": "NoUnexpectedDialog", "outcome": "no_effect", "forward
- seq=811 `perception_unsettled`: {"ts": 1785219982.3660412, "seq": 811, "run_id": "wa-forward-live-1785219745", "kind": "perception_unsettled", "status": "fail", "settled": false, "failure_modes": ["fusion_agreement_low"], "retry_str
- seq=814 `transition_eval`: {"ts": 1785219982.39342, "seq": 814, "run_id": "wa-forward-live-1785219745", "kind": "transition_eval", "status": "fail", "attempt": {"before_world_id": "w0", "after_world_id": "w0", "action_family": 
- seq=816 `verification`: {"ts": 1785219982.3940449, "seq": 816, "run_id": "wa-forward-live-1785219745", "kind": "verification", "status": "fail", "passed": false, "reason": "no_effect", "expected_predicate": "TransitionEvalua
- seq=823 `forward_predicate_rollback`: {"ts": 1785219982.5825999, "seq": 823, "run_id": "wa-forward-live-1785219745", "kind": "forward_predicate_rollback", "status": "fail", "expected": "NoUnexpectedDialog", "outcome": "no_effect", "forwar
- seq=892 `perception_unsettled`: {"ts": 1785219995.4068139, "seq": 892, "run_id": "wa-forward-live-1785219745", "kind": "perception_unsettled", "status": "fail", "settled": false, "failure_modes": ["fusion_agreement_low"], "retry_str
- seq=895 `transition_eval`: {"ts": 1785219995.4301171, "seq": 895, "run_id": "wa-forward-live-1785219745", "kind": "transition_eval", "status": "fail", "attempt": {"before_world_id": "w0", "after_world_id": "w0", "action_family"
- seq=897 `verification`: {"ts": 1785219995.430633, "seq": 897, "run_id": "wa-forward-live-1785219745", "kind": "verification", "status": "fail", "passed": false, "reason": "no_effect", "expected_predicate": "TransitionEvaluat
- seq=904 `forward_predicate_rollback`: {"ts": 1785219995.589323, "seq": 904, "run_id": "wa-forward-live-1785219745", "kind": "forward_predicate_rollback", "status": "fail", "expected": "NoUnexpectedDialog", "outcome": "no_effect", "forward
- seq=967 `perception_unsettled`: {"ts": 1785220008.912169, "seq": 967, "run_id": "wa-forward-live-1785219745", "kind": "perception_unsettled", "status": "fail", "settled": false, "failure_modes": ["fusion_agreement_low"], "retry_stra
- seq=970 `transition_eval`: {"ts": 1785220008.926466, "seq": 970, "run_id": "wa-forward-live-1785219745", "kind": "transition_eval", "status": "fail", "attempt": {"before_world_id": "w0", "after_world_id": "w0", "action_family":
- seq=972 `verification`: {"ts": 1785220008.926681, "seq": 972, "run_id": "wa-forward-live-1785219745", "kind": "verification", "status": "fail", "passed": false, "reason": "no_effect", "expected_predicate": "TransitionEvaluat
- seq=979 `forward_predicate_rollback`: {"ts": 1785220009.023672, "seq": 979, "run_id": "wa-forward-live-1785219745", "kind": "forward_predicate_rollback", "status": "fail", "expected": "NoUnexpectedDialog", "outcome": "no_effect", "forward
- seq=1042 `perception_unsettled`: {"ts": 1785220021.6033332, "seq": 1042, "run_id": "wa-forward-live-1785219745", "kind": "perception_unsettled", "status": "fail", "settled": false, "failure_modes": ["fusion_agreement_low"], "retry_st
- seq=1045 `transition_eval`: {"ts": 1785220021.617488, "seq": 1045, "run_id": "wa-forward-live-1785219745", "kind": "transition_eval", "status": "fail", "attempt": {"before_world_id": "w0", "after_world_id": "w0", "action_family"
- seq=1047 `verification`: {"ts": 1785220021.617719, "seq": 1047, "run_id": "wa-forward-live-1785219745", "kind": "verification", "status": "fail", "passed": false, "reason": "no_effect", "expected_predicate": "TransitionEvalua
- seq=1054 `forward_predicate_rollback`: {"ts": 1785220021.714632, "seq": 1054, "run_id": "wa-forward-live-1785219745", "kind": "forward_predicate_rollback", "status": "fail", "expected": "NoUnexpectedDialog", "outcome": "no_effect", "forwar
- seq=1123 `perception_unsettled`: {"ts": 1785220035.3750882, "seq": 1123, "run_id": "wa-forward-live-1785219745", "kind": "perception_unsettled", "status": "fail", "settled": false, "failure_modes": ["fusion_agreement_low"], "retry_st
- seq=1126 `transition_eval`: {"ts": 1785220035.3917792, "seq": 1126, "run_id": "wa-forward-live-1785219745", "kind": "transition_eval", "status": "fail", "attempt": {"before_world_id": "w0", "after_world_id": "w0", "action_family
- seq=1128 `verification`: {"ts": 1785220035.3923771, "seq": 1128, "run_id": "wa-forward-live-1785219745", "kind": "verification", "status": "fail", "passed": false, "reason": "no_effect", "expected_predicate": "TransitionEvalu
- seq=1135 `forward_predicate_rollback`: {"ts": 1785220035.497212, "seq": 1135, "run_id": "wa-forward-live-1785219745", "kind": "forward_predicate_rollback", "status": "fail", "expected": "NoUnexpectedDialog", "outcome": "no_effect", "forwar
- seq=1198 `perception_unsettled`: {"ts": 1785220048.866815, "seq": 1198, "run_id": "wa-forward-live-1785219745", "kind": "perception_unsettled", "status": "fail", "settled": false, "failure_modes": ["fusion_agreement_low"], "retry_str
- seq=1201 `transition_eval`: {"ts": 1785220048.892406, "seq": 1201, "run_id": "wa-forward-live-1785219745", "kind": "transition_eval", "status": "fail", "attempt": {"before_world_id": "w0", "after_world_id": "w0", "action_family"
- seq=1203 `verification`: {"ts": 1785220048.892805, "seq": 1203, "run_id": "wa-forward-live-1785219745", "kind": "verification", "status": "fail", "passed": false, "reason": "no_effect", "expected_predicate": "TransitionEvalua
- seq=1210 `forward_predicate_rollback`: {"ts": 1785220049.073272, "seq": 1210, "run_id": "wa-forward-live-1785219745", "kind": "forward_predicate_rollback", "status": "fail", "expected": "NoUnexpectedDialog", "outcome": "no_effect", "forwar
- seq=1279 `perception_unsettled`: {"ts": 1785220061.2369332, "seq": 1279, "run_id": "wa-forward-live-1785219745", "kind": "perception_unsettled", "status": "fail", "settled": false, "failure_modes": ["fusion_agreement_low"], "retry_st
- seq=1282 `transition_eval`: {"ts": 1785220061.251211, "seq": 1282, "run_id": "wa-forward-live-1785219745", "kind": "transition_eval", "status": "fail", "attempt": {"before_world_id": "w0", "after_world_id": "w0", "action_family"
- seq=1284 `verification`: {"ts": 1785220061.251425, "seq": 1284, "run_id": "wa-forward-live-1785219745", "kind": "verification", "status": "fail", "passed": false, "reason": "no_effect", "expected_predicate": "TransitionEvalua
- seq=1291 `forward_predicate_rollback`: {"ts": 1785220061.353764, "seq": 1291, "run_id": "wa-forward-live-1785219745", "kind": "forward_predicate_rollback", "status": "fail", "expected": "NoUnexpectedDialog", "outcome": "no_effect", "forwar
- seq=1354 `perception_unsettled`: {"ts": 1785220078.476398, "seq": 1354, "run_id": "wa-forward-live-1785219745", "kind": "perception_unsettled", "status": "fail", "settled": false, "failure_modes": ["fusion_agreement_low"], "retry_str
- seq=1357 `transition_eval`: {"ts": 1785220078.4940228, "seq": 1357, "run_id": "wa-forward-live-1785219745", "kind": "transition_eval", "status": "fail", "attempt": {"before_world_id": "w0", "after_world_id": "w0", "action_family
- seq=1359 `verification`: {"ts": 1785220078.4942982, "seq": 1359, "run_id": "wa-forward-live-1785219745", "kind": "verification", "status": "fail", "passed": false, "reason": "no_effect", "expected_predicate": "TransitionEvalu
- seq=1366 `forward_predicate_rollback`: {"ts": 1785220078.604047, "seq": 1366, "run_id": "wa-forward-live-1785219745", "kind": "forward_predicate_rollback", "status": "fail", "expected": "NoUnexpectedDialog", "outcome": "no_effect", "forwar
- seq=1435 `perception_unsettled`: {"ts": 1785220094.365987, "seq": 1435, "run_id": "wa-forward-live-1785219745", "kind": "perception_unsettled", "status": "fail", "settled": false, "failure_modes": ["fusion_agreement_low"], "retry_str
- seq=1438 `transition_eval`: {"ts": 1785220094.392813, "seq": 1438, "run_id": "wa-forward-live-1785219745", "kind": "transition_eval", "status": "fail", "attempt": {"before_world_id": "w0", "after_world_id": "w0", "action_family"
- seq=1440 `verification`: {"ts": 1785220094.393327, "seq": 1440, "run_id": "wa-forward-live-1785219745", "kind": "verification", "status": "fail", "passed": false, "reason": "no_effect", "expected_predicate": "TransitionEvalua
- seq=1447 `forward_predicate_rollback`: {"ts": 1785220094.577898, "seq": 1447, "run_id": "wa-forward-live-1785219745", "kind": "forward_predicate_rollback", "status": "fail", "expected": "NoUnexpectedDialog", "outcome": "no_effect", "forwar
- seq=1504 `perception_unsettled`: {"ts": 1785220108.91935, "seq": 1504, "run_id": "wa-forward-live-1785219745", "kind": "perception_unsettled", "status": "fail", "settled": false, "failure_modes": ["fusion_agreement_low"], "retry_stra
- seq=1507 `transition_eval`: {"ts": 1785220108.9609542, "seq": 1507, "run_id": "wa-forward-live-1785219745", "kind": "transition_eval", "status": "fail", "attempt": {"before_world_id": "w0", "after_world_id": "w0", "action_family
- seq=1509 `verification`: {"ts": 1785220108.9618502, "seq": 1509, "run_id": "wa-forward-live-1785219745", "kind": "verification", "status": "fail", "passed": false, "reason": "no_effect", "expected_predicate": "TransitionEvalu
- seq=1516 `forward_predicate_rollback`: {"ts": 1785220109.258493, "seq": 1516, "run_id": "wa-forward-live-1785219745", "kind": "forward_predicate_rollback", "status": "fail", "expected": "NoUnexpectedDialog", "outcome": "no_effect", "forwar
- seq=1585 `perception_unsettled`: {"ts": 1785220122.414338, "seq": 1585, "run_id": "wa-forward-live-1785219745", "kind": "perception_unsettled", "status": "fail", "settled": false, "failure_modes": ["fusion_agreement_low"], "retry_str
- seq=1588 `transition_eval`: {"ts": 1785220122.438633, "seq": 1588, "run_id": "wa-forward-live-1785219745", "kind": "transition_eval", "status": "fail", "attempt": {"before_world_id": "w0", "after_world_id": "w0", "action_family"
- seq=1590 `verification`: {"ts": 1785220122.4390981, "seq": 1590, "run_id": "wa-forward-live-1785219745", "kind": "verification", "status": "fail", "passed": false, "reason": "no_effect", "expected_predicate": "TransitionEvalu
- seq=1597 `forward_predicate_rollback`: {"ts": 1785220122.622288, "seq": 1597, "run_id": "wa-forward-live-1785219745", "kind": "forward_predicate_rollback", "status": "fail", "expected": "NoUnexpectedDialog", "outcome": "no_effect", "forwar
- seq=1660 `perception_unsettled`: {"ts": 1785220136.2666602, "seq": 1660, "run_id": "wa-forward-live-1785219745", "kind": "perception_unsettled", "status": "fail", "settled": false, "failure_modes": ["fusion_agreement_low"], "retry_st
- seq=1663 `transition_eval`: {"ts": 1785220136.2927449, "seq": 1663, "run_id": "wa-forward-live-1785219745", "kind": "transition_eval", "status": "fail", "attempt": {"before_world_id": "w0", "after_world_id": "w0", "action_family
- seq=1665 `verification`: {"ts": 1785220136.293213, "seq": 1665, "run_id": "wa-forward-live-1785219745", "kind": "verification", "status": "fail", "passed": false, "reason": "no_effect", "expected_predicate": "TransitionEvalua
- seq=1672 `forward_predicate_rollback`: {"ts": 1785220136.696745, "seq": 1672, "run_id": "wa-forward-live-1785219745", "kind": "forward_predicate_rollback", "status": "fail", "expected": "NoUnexpectedDialog", "outcome": "no_effect", "forwar
- seq=1735 `perception_unsettled`: {"ts": 1785220151.1692228, "seq": 1735, "run_id": "wa-forward-live-1785219745", "kind": "perception_unsettled", "status": "fail", "settled": false, "failure_modes": ["fusion_agreement_low"], "retry_st
- seq=1738 `transition_eval`: {"ts": 1785220151.1954, "seq": 1738, "run_id": "wa-forward-live-1785219745", "kind": "transition_eval", "status": "fail", "attempt": {"before_world_id": "w0", "after_world_id": "w0", "action_family": 
- seq=1740 `verification`: {"ts": 1785220151.195808, "seq": 1740, "run_id": "wa-forward-live-1785219745", "kind": "verification", "status": "fail", "passed": false, "reason": "no_effect", "expected_predicate": "TransitionEvalua
- seq=1747 `forward_predicate_rollback`: {"ts": 1785220151.393057, "seq": 1747, "run_id": "wa-forward-live-1785219745", "kind": "forward_predicate_rollback", "status": "fail", "expected": "NoUnexpectedDialog", "outcome": "no_effect", "forwar
- seq=1816 `perception_unsettled`: {"ts": 1785220164.8036401, "seq": 1816, "run_id": "wa-forward-live-1785219745", "kind": "perception_unsettled", "status": "fail", "settled": false, "failure_modes": ["fusion_agreement_low"], "retry_st
- seq=1819 `transition_eval`: {"ts": 1785220164.820586, "seq": 1819, "run_id": "wa-forward-live-1785219745", "kind": "transition_eval", "status": "fail", "attempt": {"before_world_id": "w0", "after_world_id": "w0", "action_family"
- seq=1821 `verification`: {"ts": 1785220164.8209128, "seq": 1821, "run_id": "wa-forward-live-1785219745", "kind": "verification", "status": "fail", "passed": false, "reason": "no_effect", "expected_predicate": "TransitionEvalu
- seq=1828 `forward_predicate_rollback`: {"ts": 1785220164.961441, "seq": 1828, "run_id": "wa-forward-live-1785219745", "kind": "forward_predicate_rollback", "status": "fail", "expected": "NoUnexpectedDialog", "outcome": "no_effect", "forwar
- seq=1891 `perception_unsettled`: {"ts": 1785220177.2118468, "seq": 1891, "run_id": "wa-forward-live-1785219745", "kind": "perception_unsettled", "status": "fail", "settled": false, "failure_modes": ["fusion_agreement_low"], "retry_st
- seq=1894 `transition_eval`: {"ts": 1785220177.234396, "seq": 1894, "run_id": "wa-forward-live-1785219745", "kind": "transition_eval", "status": "fail", "attempt": {"before_world_id": "w0", "after_world_id": "w0", "action_family"
- seq=1896 `verification`: {"ts": 1785220177.234814, "seq": 1896, "run_id": "wa-forward-live-1785219745", "kind": "verification", "status": "fail", "passed": false, "reason": "no_effect", "expected_predicate": "TransitionEvalua
- seq=1903 `forward_predicate_rollback`: {"ts": 1785220177.77888, "seq": 1903, "run_id": "wa-forward-live-1785219745", "kind": "forward_predicate_rollback", "status": "fail", "expected": "NoUnexpectedDialog", "outcome": "no_effect", "forward
- seq=1966 `perception_unsettled`: {"ts": 1785220193.687041, "seq": 1966, "run_id": "wa-forward-live-1785219745", "kind": "perception_unsettled", "status": "fail", "settled": false, "failure_modes": ["fusion_agreement_low"], "retry_str
- seq=1969 `transition_eval`: {"ts": 1785220193.71037, "seq": 1969, "run_id": "wa-forward-live-1785219745", "kind": "transition_eval", "status": "fail", "attempt": {"before_world_id": "w0", "after_world_id": "w0", "action_family":
- seq=1971 `verification`: {"ts": 1785220193.711064, "seq": 1971, "run_id": "wa-forward-live-1785219745", "kind": "verification", "status": "fail", "passed": false, "reason": "no_effect", "expected_predicate": "TransitionEvalua
- seq=1978 `forward_predicate_rollback`: {"ts": 1785220194.134242, "seq": 1978, "run_id": "wa-forward-live-1785219745", "kind": "forward_predicate_rollback", "status": "fail", "expected": "NoUnexpectedDialog", "outcome": "no_effect", "forwar
- seq=2047 `perception_unsettled`: {"ts": 1785220205.815994, "seq": 2047, "run_id": "wa-forward-live-1785219745", "kind": "perception_unsettled", "status": "fail", "settled": false, "failure_modes": ["fusion_agreement_low"], "retry_str
- seq=2050 `transition_eval`: {"ts": 1785220205.8307378, "seq": 2050, "run_id": "wa-forward-live-1785219745", "kind": "transition_eval", "status": "fail", "attempt": {"before_world_id": "w0", "after_world_id": "w0", "action_family
- seq=2052 `verification`: {"ts": 1785220205.8311412, "seq": 2052, "run_id": "wa-forward-live-1785219745", "kind": "verification", "status": "fail", "passed": false, "reason": "no_effect", "expected_predicate": "TransitionEvalu
- seq=2059 `forward_predicate_rollback`: {"ts": 1785220205.9294431, "seq": 2059, "run_id": "wa-forward-live-1785219745", "kind": "forward_predicate_rollback", "status": "fail", "expected": "NoUnexpectedDialog", "outcome": "no_effect", "forwa
- seq=2128 `perception_unsettled`: {"ts": 1785220218.5699148, "seq": 2128, "run_id": "wa-forward-live-1785219745", "kind": "perception_unsettled", "status": "fail", "settled": false, "failure_modes": ["fusion_agreement_low"], "retry_st
- seq=2131 `transition_eval`: {"ts": 1785220218.5903192, "seq": 2131, "run_id": "wa-forward-live-1785219745", "kind": "transition_eval", "status": "fail", "attempt": {"before_world_id": "w0", "after_world_id": "w0", "action_family
- seq=2133 `verification`: {"ts": 1785220218.590718, "seq": 2133, "run_id": "wa-forward-live-1785219745", "kind": "verification", "status": "fail", "passed": false, "reason": "no_effect", "expected_predicate": "TransitionEvalua
- seq=2140 `forward_predicate_rollback`: {"ts": 1785220219.016789, "seq": 2140, "run_id": "wa-forward-live-1785219745", "kind": "forward_predicate_rollback", "status": "fail", "expected": "NoUnexpectedDialog", "outcome": "no_effect", "forwar
- seq=2197 `perception_unsettled`: {"ts": 1785220234.297676, "seq": 2197, "run_id": "wa-forward-live-1785219745", "kind": "perception_unsettled", "status": "fail", "settled": false, "failure_modes": ["fusion_agreement_low"], "retry_str
- seq=2200 `transition_eval`: {"ts": 1785220234.31843, "seq": 2200, "run_id": "wa-forward-live-1785219745", "kind": "transition_eval", "status": "fail", "attempt": {"before_world_id": "w0", "after_world_id": "w0", "action_family":
- seq=2202 `verification`: {"ts": 1785220234.318797, "seq": 2202, "run_id": "wa-forward-live-1785219745", "kind": "verification", "status": "fail", "passed": false, "reason": "no_effect", "expected_predicate": "TransitionEvalua
- seq=2209 `forward_predicate_rollback`: {"ts": 1785220234.4615319, "seq": 2209, "run_id": "wa-forward-live-1785219745", "kind": "forward_predicate_rollback", "status": "fail", "expected": "NoUnexpectedDialog", "outcome": "no_effect", "forwa
- seq=2272 `perception_unsettled`: {"ts": 1785220247.454439, "seq": 2272, "run_id": "wa-forward-live-1785219745", "kind": "perception_unsettled", "status": "fail", "settled": false, "failure_modes": ["fusion_agreement_low"], "retry_str
- seq=2275 `transition_eval`: {"ts": 1785220247.489417, "seq": 2275, "run_id": "wa-forward-live-1785219745", "kind": "transition_eval", "status": "fail", "attempt": {"before_world_id": "w0", "after_world_id": "w0", "action_family"
- seq=2277 `verification`: {"ts": 1785220247.4901052, "seq": 2277, "run_id": "wa-forward-live-1785219745", "kind": "verification", "status": "fail", "passed": false, "reason": "no_effect", "expected_predicate": "TransitionEvalu
- seq=2284 `forward_predicate_rollback`: {"ts": 1785220247.9298592, "seq": 2284, "run_id": "wa-forward-live-1785219745", "kind": "forward_predicate_rollback", "status": "fail", "expected": "NoUnexpectedDialog", "outcome": "no_effect", "forwa
- seq=2341 `perception_unsettled`: {"ts": 1785220261.27525, "seq": 2341, "run_id": "wa-forward-live-1785219745", "kind": "perception_unsettled", "status": "fail", "settled": false, "failure_modes": ["fusion_agreement_low"], "retry_stra
- seq=2344 `transition_eval`: {"ts": 1785220261.310064, "seq": 2344, "run_id": "wa-forward-live-1785219745", "kind": "transition_eval", "status": "fail", "attempt": {"before_world_id": "w0", "after_world_id": "w0", "action_family"
- seq=2346 `verification`: {"ts": 1785220261.311233, "seq": 2346, "run_id": "wa-forward-live-1785219745", "kind": "verification", "status": "fail", "passed": false, "reason": "no_effect", "expected_predicate": "TransitionEvalua
- seq=2353 `forward_predicate_rollback`: {"ts": 1785220261.630058, "seq": 2353, "run_id": "wa-forward-live-1785219745", "kind": "forward_predicate_rollback", "status": "fail", "expected": "NoUnexpectedDialog", "outcome": "no_effect", "forwar
- seq=2416 `perception_unsettled`: {"ts": 1785220279.987245, "seq": 2416, "run_id": "wa-forward-live-1785219745", "kind": "perception_unsettled", "status": "fail", "settled": false, "failure_modes": ["fusion_agreement_low"], "retry_str
- seq=2419 `transition_eval`: {"ts": 1785220280.026585, "seq": 2419, "run_id": "wa-forward-live-1785219745", "kind": "transition_eval", "status": "fail", "attempt": {"before_world_id": "w0", "after_world_id": "w0", "action_family"
- seq=2421 `verification`: {"ts": 1785220280.027343, "seq": 2421, "run_id": "wa-forward-live-1785219745", "kind": "verification", "status": "fail", "passed": false, "reason": "no_effect", "expected_predicate": "TransitionEvalua
- seq=2428 `forward_predicate_rollback`: {"ts": 1785220280.351815, "seq": 2428, "run_id": "wa-forward-live-1785219745", "kind": "forward_predicate_rollback", "status": "fail", "expected": "NoUnexpectedDialog", "outcome": "no_effect", "forwar
- seq=2491 `perception_unsettled`: {"ts": 1785220295.864149, "seq": 2491, "run_id": "wa-forward-live-1785219745", "kind": "perception_unsettled", "status": "fail", "settled": false, "failure_modes": ["fusion_agreement_low"], "retry_str
- seq=2494 `transition_eval`: {"ts": 1785220295.891284, "seq": 2494, "run_id": "wa-forward-live-1785219745", "kind": "transition_eval", "status": "fail", "attempt": {"before_world_id": "w0", "after_world_id": "w0", "action_family"
- seq=2496 `verification`: {"ts": 1785220295.891885, "seq": 2496, "run_id": "wa-forward-live-1785219745", "kind": "verification", "status": "fail", "passed": false, "reason": "no_effect", "expected_predicate": "TransitionEvalua
- seq=2503 `forward_predicate_rollback`: {"ts": 1785220296.103325, "seq": 2503, "run_id": "wa-forward-live-1785219745", "kind": "forward_predicate_rollback", "status": "fail", "expected": "NoUnexpectedDialog", "outcome": "no_effect", "forwar
- seq=2529 `check`: {"ts": 1785220300.2004511, "seq": 2529, "run_id": "wa-forward-live-1785219745", "kind": "check", "status": "fail", "name": "forward_task", "expected": "forward 'zarooratwala' from 'Kulvinder' to 'Pall
- seq=2530 `run_end`: {"ts": 1785220300.200604, "seq": 2530, "run_id": "wa-forward-live-1785219745", "kind": "run_end", "status": "fail", "ok": false, "detail": "closed_loop ok=False reason='Maximum step count reached' ite
