# Run log — `wa-forward-live-1785214544`

- JSONL: `plugin/experiments/runs/forward_zarooratwala_live_20260728_102544.jsonl`
- Events: 2585

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
| 13 | ok | world_patch | conversation |
| 14 | ok | step | closed-loop goal=find the zarooratwala link sent to kulvinder on whatsapp and forward to pallavi |
| 15 | ok | loop_budget |  |
| 16 | ok | step | app=WhatsApp screenshot=True |
| 17 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 18 | ok | step | sources=['pyobjc_ax', 'macapptree'] agreement=0.7 |
| 19 | ok | observation |  |
| 20 | ok | observation |  |
| 21 | ok | storage_cleanup |  |
| 22 | ok | step | storage pressure cleanup |
| 23 | ok | step | app=WhatsApp screenshot=True |
| 24 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 25 | ok | step | sources=['pyobjc_ax', 'macapptree'] agreement=0.7 |
| 26 | ok | observation |  |
| 27 | ok | observation |  |
| 28 | ok | forward_task |  |
| 29 | ok | world_patch | conversation |
| 30 | ok | goal_status |  |
| 31 | ok | decision_engine |  |
| 32 | ok | planner_decision |  |
| 33 | fail | execution | no editable field confirmed for 'Kulvinder'; attempts=['open=pressed Search via AXPress', 'editable_field=missing', 'ope |
| 34 | fail | transition_attribution |  |
| 35 | ok | step | app=WhatsApp screenshot=True |
| 36 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 37 | ok | step | sources=['pyobjc_ax', 'macapptree'] agreement=0.7 |
| 38 | ok | observation |  |
| 39 | ok | observation |  |
| 40 | ok | forward_task |  |
| 41 | ok | world_patch | conversation |
| 42 | ok | fusion_conflicts |  |
| 43 | ok | goal_status |  |
| 44 | ok | decision_engine |  |
| 45 | ok | planner_decision |  |
| 46 | ok | execution | open Search via pressed Search via AXPress |
| 47 | ok | step | transition settle |
| 48 | ok | step | app=WhatsApp screenshot=True |
| 49 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 50 | ok | step | sources=['pyobjc_ax', 'macapptree'] agreement=0.7 |
| 51 | ok | observation |  |
| 52 | ok | step | transition poll |
| 53 | ok | step | app=WhatsApp screenshot=True |
| 54 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 55 | ok | step | sources=['pyobjc_ax', 'macapptree'] agreement=0.7 |
| 56 | ok | observation |  |
| 57 | ok | step | transition poll |
| 58 | ok | perception_retry |  |
| 59 | ok | step | perception retry (fusion_agreement_low) |
| 60 | ok | perception_retry_mode |  |
| 61 | ok | step | app=WhatsApp screenshot=True |
| 62 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 63 | ok | step | sources=['pyobjc_ax', 'macapptree'] agreement=0.7 |
| 64 | ok | observation |  |
| 65 | fail | perception_unsettled |  |
| 66 | ok | post_observation |  |
| 67 | ok | post_world_patch |  |
| 68 | fail | transition_eval |  |
| 69 | ok | transition_attribution |  |
| 70 | fail | verification |  |
| 71 | ok | step | app=WhatsApp screenshot=True |
| 72 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 73 | ok | step | sources=['pyobjc_ax', 'macapptree'] agreement=0.7 |
| 74 | ok | observation |  |
| 75 | ok | post_transition_richer_reobserve |  |
| 76 | fail | forward_predicate_rollback |  |
| 77 | ok | step | app=WhatsApp screenshot=True |
| 78 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 79 | ok | step | sources=['pyobjc_ax', 'macapptree'] agreement=0.7 |
| 80 | ok | observation |  |
| 81 | ok | observation |  |
| 82 | ok | forward_task |  |
| 83 | ok | world_patch | conversation |
| 84 | ok | fusion_conflicts |  |
| 85 | ok | goal_status |  |
| 86 | ok | decision_engine |  |
| 87 | ok | planner_decision |  |
| 88 | ok | step | re-perceive current world (actuation/world uncertainty) |
| 89 | ok | step | app=WhatsApp screenshot=True |
| 90 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 91 | ok | step | sources=['pyobjc_ax', 'macapptree'] agreement=0.7 |
| 92 | ok | observation |  |
| 93 | ok | observation |  |
| 94 | ok | forward_task |  |
| 95 | ok | world_patch | conversation |
| 96 | ok | fusion_conflicts |  |
| 97 | ok | goal_status |  |
| 98 | ok | decision_engine |  |
| 99 | ok | planner_decision |  |
| 100 | ok | step | re-perceive current world (actuation/world uncertainty) |
| 101 | ok | step | app=WhatsApp screenshot=True |
| 102 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 103 | ok | step | sources=['pyobjc_ax', 'macapptree'] agreement=0.7 |
| 104 | ok | observation |  |
| 105 | ok | observation |  |
| 106 | ok | forward_task |  |
| 107 | ok | world_patch | conversation |
| 108 | ok | fusion_conflicts |  |
| 109 | ok | goal_status |  |
| 110 | ok | decision_engine |  |
| 111 | ok | planner_decision |  |
| 112 | fail | execution | no editable field confirmed for 'Kulvinder'; attempts=['open=pressed Search via AXPress', 'editable_field=missing', 'ope |
| 113 | fail | transition_attribution |  |
| 114 | ok | step | app=WhatsApp screenshot=True |
| 115 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 116 | ok | step | sources=['pyobjc_ax', 'macapptree'] agreement=0.7 |
| 117 | ok | observation |  |
| 118 | ok | observation |  |
| 119 | ok | forward_task |  |
| 120 | ok | world_patch | conversation |
| 121 | ok | goal_status |  |
| 122 | ok | decision_engine |  |
| 123 | ok | planner_decision |  |
| 124 | ok | execution | open Search via pressed Search via AXPress |
| 125 | ok | step | transition settle |
| 126 | ok | step | app=WhatsApp screenshot=True |
| 127 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 128 | ok | step | sources=['pyobjc_ax', 'macapptree'] agreement=0.7 |
| 129 | ok | observation |  |
| 130 | ok | step | transition poll |
| 131 | ok | step | app=WhatsApp screenshot=True |
| 132 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 133 | ok | step | sources=['pyobjc_ax', 'macapptree'] agreement=0.7 |
| 134 | ok | observation |  |
| 135 | ok | step | transition poll |
| 136 | ok | perception_retry |  |
| 137 | ok | step | perception retry (fusion_agreement_low) |
| 138 | ok | perception_retry_mode |  |
| 139 | ok | step | app=WhatsApp screenshot=True |
| 140 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 141 | ok | step | sources=['pyobjc_ax', 'macapptree'] agreement=0.7 |
| 142 | ok | observation |  |
| 143 | fail | perception_unsettled |  |
| 144 | ok | post_observation |  |
| 145 | ok | post_world_patch |  |
| 146 | fail | transition_eval |  |
| 147 | ok | transition_attribution |  |
| 148 | fail | verification |  |
| 149 | ok | step | app=WhatsApp screenshot=True |
| 150 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 151 | ok | step | sources=['pyobjc_ax', 'macapptree'] agreement=0.7 |
| 152 | ok | observation |  |
| 153 | ok | post_transition_richer_reobserve |  |
| 154 | fail | forward_predicate_rollback |  |
| 155 | ok | step | app=WhatsApp screenshot=True |
| 156 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 157 | ok | step | sources=['pyobjc_ax', 'macapptree'] agreement=0.7 |
| 158 | ok | observation |  |
| 159 | ok | observation |  |
| 160 | ok | forward_task |  |
| 161 | ok | world_patch | conversation |
| 162 | ok | goal_status |  |
| 163 | ok | decision_engine |  |
| 164 | ok | planner_decision |  |
| 165 | ok | step | re-perceive current world (actuation/world uncertainty) |
| 166 | ok | step | app=WhatsApp screenshot=True |
| 167 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 168 | ok | step | sources=['pyobjc_ax', 'macapptree'] agreement=0.7 |
| 169 | ok | observation |  |
| 170 | ok | observation |  |
| 171 | ok | forward_task |  |
| 172 | ok | world_patch | conversation |
| 173 | ok | goal_status |  |
| 174 | ok | decision_engine |  |
| 175 | ok | planner_decision |  |
| 176 | ok | step | re-perceive current world (actuation/world uncertainty) |
| 177 | ok | step | app=WhatsApp screenshot=True |
| 178 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 179 | ok | step | sources=['pyobjc_ax', 'macapptree'] agreement=0.7 |
| 180 | ok | observation |  |
| 181 | ok | observation |  |
| 182 | ok | forward_task |  |
| 183 | ok | world_patch | conversation |
| 184 | ok | goal_status |  |
| 185 | ok | decision_engine |  |
| 186 | ok | planner_decision |  |
| 187 | fail | execution | no editable field confirmed for 'Kulvinder'; attempts=['open=pressed Search via AXPress', 'editable_field=missing', 'ope |
| 188 | fail | transition_attribution |  |
| 189 | ok | step | app=WhatsApp screenshot=True |
| 190 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 191 | ok | step | sources=['pyobjc_ax', 'macapptree'] agreement=0.7 |
| 192 | ok | observation |  |
| 193 | ok | observation |  |
| 194 | ok | forward_task |  |
| 195 | ok | world_patch | conversation |
| 196 | ok | fusion_conflicts |  |
| 197 | ok | goal_status |  |
| 198 | ok | decision_engine |  |
| 199 | ok | planner_decision |  |
| 200 | ok | execution | pressed Escape |
| 201 | ok | step | transition settle |
| 202 | ok | step | app=WhatsApp screenshot=True |
| 203 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 204 | ok | step | sources=['pyobjc_ax', 'macapptree'] agreement=0.7 |
| 205 | ok | observation |  |
| 206 | ok | step | transition poll |
| 207 | ok | step | app=WhatsApp screenshot=True |
| 208 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 209 | ok | step | sources=['pyobjc_ax', 'macapptree'] agreement=0.7 |
| 210 | ok | observation |  |
| 211 | ok | step | transition poll |
| 212 | ok | perception_retry |  |
| 213 | ok | step | perception retry (fusion_agreement_low) |
| 214 | ok | perception_retry_mode |  |
| 215 | ok | step | app=WhatsApp screenshot=True |
| 216 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 217 | ok | step | sources=['pyobjc_ax', 'macapptree'] agreement=0.7 |
| 218 | ok | observation |  |
| 219 | fail | perception_unsettled |  |
| 220 | ok | post_observation |  |
| 221 | ok | post_world_patch |  |
| 222 | fail | transition_eval |  |
| 223 | ok | transition_attribution |  |
| 224 | fail | verification |  |
| 225 | ok | step | app=WhatsApp screenshot=True |
| 226 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 227 | ok | step | sources=['pyobjc_ax', 'macapptree'] agreement=0.7 |
| 228 | ok | observation |  |
| 229 | ok | post_transition_richer_reobserve |  |
| 230 | fail | forward_predicate_rollback |  |
| 231 | ok | step | app=WhatsApp screenshot=True |
| 232 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 233 | ok | step | sources=['pyobjc_ax', 'macapptree'] agreement=0.7 |
| 234 | ok | observation |  |
| 235 | ok | observation |  |
| 236 | ok | forward_task |  |
| 237 | ok | world_patch | conversation |
| 238 | ok | fusion_conflicts |  |
| 239 | ok | goal_status |  |
| 240 | ok | decision_engine |  |
| 241 | ok | planner_decision |  |
| 242 | ok | execution | open Search via pressed Search via AXPress |
| 243 | ok | step | transition settle |
| 244 | ok | step | app=WhatsApp screenshot=True |
| 245 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 246 | ok | step | sources=['pyobjc_ax', 'macapptree'] agreement=0.7 |
| 247 | ok | observation |  |
| 248 | ok | step | transition poll |
| 249 | ok | step | app=WhatsApp screenshot=True |
| 250 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 251 | ok | step | sources=['pyobjc_ax', 'macapptree'] agreement=0.7 |
| 252 | ok | observation |  |
| 253 | ok | step | transition poll |
| 254 | ok | perception_retry |  |
| 255 | ok | step | perception retry (fusion_agreement_low) |
| 256 | ok | perception_retry_mode |  |
| 257 | ok | step | app=WhatsApp screenshot=True |
| 258 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 259 | ok | step | sources=['pyobjc_ax', 'macapptree'] agreement=0.7 |
| 260 | ok | observation |  |
| 261 | fail | perception_unsettled |  |
| 262 | ok | post_observation |  |
| 263 | ok | post_world_patch |  |
| 264 | fail | transition_eval |  |
| 265 | ok | transition_attribution |  |
| 266 | fail | verification |  |
| 267 | ok | step | app=WhatsApp screenshot=True |
| 268 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 269 | ok | step | sources=['pyobjc_ax', 'macapptree'] agreement=0.7 |
| 270 | ok | observation |  |
| 271 | ok | post_transition_richer_reobserve |  |
| 272 | fail | forward_predicate_rollback |  |
| 273 | ok | step | app=WhatsApp screenshot=True |
| 274 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 275 | ok | step | sources=['pyobjc_ax', 'macapptree'] agreement=0.7 |
| 276 | ok | observation |  |
| 277 | ok | observation |  |
| 278 | ok | forward_task |  |
| 279 | ok | world_patch | conversation |
| 280 | ok | fusion_conflicts |  |
| 281 | ok | goal_status |  |
| 282 | ok | decision_engine |  |
| 283 | ok | planner_decision |  |
| 284 | ok | step | re-perceive current world (actuation/world uncertainty) |
| 285 | ok | step | app=WhatsApp screenshot=True |
| 286 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 287 | ok | step | sources=['pyobjc_ax', 'macapptree'] agreement=0.7 |
| 288 | ok | observation |  |
| 289 | ok | observation |  |
| 290 | ok | forward_task |  |
| 291 | ok | world_patch | conversation |
| 292 | ok | fusion_conflicts |  |
| 293 | ok | goal_status |  |
| 294 | ok | decision_engine |  |
| 295 | ok | planner_decision |  |
| 296 | ok | execution | pressed Escape |
| 297 | ok | step | transition settle |
| 298 | ok | step | app=WhatsApp screenshot=True |
| 299 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 300 | ok | step | sources=['pyobjc_ax', 'macapptree'] agreement=0.7 |
| 301 | ok | observation |  |
| 302 | ok | step | transition poll |
| 303 | ok | step | app=WhatsApp screenshot=True |
| 304 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 305 | ok | step | sources=['pyobjc_ax', 'macapptree'] agreement=0.7 |
| 306 | ok | observation |  |
| 307 | ok | step | transition poll |
| 308 | ok | perception_retry |  |
| 309 | ok | step | perception retry (fusion_agreement_low) |
| 310 | ok | perception_retry_mode |  |
| 311 | ok | step | app=WhatsApp screenshot=True |
| 312 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 313 | ok | step | sources=['pyobjc_ax', 'macapptree'] agreement=0.7 |
| 314 | ok | observation |  |
| 315 | fail | perception_unsettled |  |
| 316 | ok | post_observation |  |
| 317 | ok | post_world_patch |  |
| 318 | fail | transition_eval |  |
| 319 | ok | transition_attribution |  |
| 320 | fail | verification |  |
| 321 | ok | step | app=WhatsApp screenshot=True |
| 322 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 323 | ok | step | sources=['pyobjc_ax', 'macapptree'] agreement=0.7 |
| 324 | ok | observation |  |
| 325 | ok | post_transition_richer_reobserve |  |
| 326 | fail | forward_predicate_rollback |  |
| 327 | ok | step | app=WhatsApp screenshot=True |
| 328 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 329 | ok | step | sources=['pyobjc_ax', 'macapptree'] agreement=0.7 |
| 330 | ok | observation |  |
| 331 | ok | observation |  |
| 332 | ok | forward_task |  |
| 333 | ok | world_patch | conversation |
| 334 | ok | fusion_conflicts |  |
| 335 | ok | goal_status |  |
| 336 | ok | decision_engine |  |
| 337 | ok | planner_decision |  |
| 338 | fail | execution | no editable field confirmed for 'Kulvinder'; attempts=['open=pressed Search via AXPress', 'editable_field=missing', 'ope |
| 339 | fail | transition_attribution |  |
| 340 | ok | step | app=WhatsApp screenshot=True |
| 341 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 342 | ok | step | sources=['pyobjc_ax', 'macapptree'] agreement=0.7 |
| 343 | ok | observation |  |
| 344 | ok | observation |  |
| 345 | ok | forward_task |  |
| 346 | ok | world_patch | conversation |
| 347 | ok | fusion_conflicts |  |
| 348 | ok | goal_status |  |
| 349 | ok | decision_engine |  |
| 350 | ok | planner_decision |  |
| 351 | ok | execution | open Search via pressed Search via AXPress |
| 352 | ok | step | transition settle |
| 353 | ok | step | app=WhatsApp screenshot=True |
| 354 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 355 | ok | step | sources=['pyobjc_ax', 'macapptree'] agreement=0.7 |
| 356 | ok | observation |  |
| 357 | ok | step | transition poll |
| 358 | ok | step | app=WhatsApp screenshot=True |
| 359 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 360 | ok | step | sources=['pyobjc_ax', 'macapptree'] agreement=0.7 |
| 361 | ok | observation |  |
| 362 | ok | step | transition poll |
| 363 | ok | perception_retry |  |
| 364 | ok | step | perception retry (fusion_agreement_low) |
| 365 | ok | perception_retry_mode |  |
| 366 | ok | step | app=WhatsApp screenshot=True |
| 367 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 368 | ok | step | sources=['pyobjc_ax', 'macapptree'] agreement=0.7 |
| 369 | ok | observation |  |
| 370 | fail | perception_unsettled |  |
| 371 | ok | post_observation |  |
| 372 | ok | post_world_patch |  |
| 373 | fail | transition_eval |  |
| 374 | ok | transition_attribution |  |
| 375 | fail | verification |  |
| 376 | ok | step | app=WhatsApp screenshot=True |
| 377 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 378 | ok | step | sources=['pyobjc_ax', 'macapptree'] agreement=0.7 |
| 379 | ok | observation |  |
| 380 | ok | post_transition_richer_reobserve |  |
| 381 | fail | forward_predicate_rollback |  |
| 382 | ok | step | app=WhatsApp screenshot=True |
| 383 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 384 | ok | step | sources=['pyobjc_ax', 'macapptree'] agreement=0.7 |
| 385 | ok | observation |  |
| 386 | ok | observation |  |
| 387 | ok | forward_task |  |
| 388 | ok | world_patch | conversation |
| 389 | ok | fusion_conflicts |  |
| 390 | ok | goal_status |  |
| 391 | ok | decision_engine |  |
| 392 | ok | planner_decision |  |
| 393 | ok | execution | pressed Escape |
| 394 | ok | step | transition settle |
| 395 | ok | step | app=WhatsApp screenshot=True |
| 396 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 397 | ok | step | sources=['pyobjc_ax', 'macapptree'] agreement=0.7 |
| 398 | ok | observation |  |
| 399 | ok | step | transition poll |
| 400 | ok | step | app=WhatsApp screenshot=True |
| 401 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 402 | ok | step | sources=['pyobjc_ax', 'macapptree'] agreement=0.7 |
| 403 | ok | observation |  |
| 404 | ok | step | transition poll |
| 405 | ok | perception_retry |  |
| 406 | ok | step | perception retry (fusion_agreement_low) |
| 407 | ok | perception_retry_mode |  |
| 408 | ok | step | app=WhatsApp screenshot=True |
| 409 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 410 | ok | step | sources=['pyobjc_ax', 'macapptree'] agreement=0.7 |
| 411 | ok | observation |  |
| 412 | fail | perception_unsettled |  |
| 413 | ok | post_observation |  |
| 414 | ok | post_world_patch |  |
| 415 | fail | transition_eval |  |
| 416 | ok | transition_attribution |  |
| 417 | fail | verification |  |
| 418 | ok | step | app=WhatsApp screenshot=True |
| 419 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 420 | ok | step | sources=['pyobjc_ax', 'macapptree'] agreement=0.7 |
| 421 | ok | observation |  |
| 422 | ok | post_transition_richer_reobserve |  |
| 423 | fail | forward_predicate_rollback |  |
| 424 | ok | step | app=WhatsApp screenshot=True |
| 425 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 426 | ok | step | sources=['pyobjc_ax', 'macapptree'] agreement=0.7 |
| 427 | ok | observation |  |
| 428 | ok | observation |  |
| 429 | ok | forward_task |  |
| 430 | ok | world_patch | conversation |
| 431 | ok | fusion_conflicts |  |
| 432 | ok | goal_status |  |
| 433 | ok | decision_engine |  |
| 434 | ok | planner_decision |  |
| 435 | ok | step | re-perceive current world (actuation/world uncertainty) |
| 436 | ok | step | app=WhatsApp screenshot=True |
| 437 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 438 | ok | step | sources=['pyobjc_ax', 'macapptree'] agreement=0.7 |
| 439 | ok | observation |  |
| 440 | ok | observation |  |
| 441 | ok | forward_task |  |
| 442 | ok | world_patch | conversation |
| 443 | ok | fusion_conflicts |  |
| 444 | ok | goal_status |  |
| 445 | ok | decision_engine |  |
| 446 | ok | planner_decision |  |
| 447 | fail | execution | no editable field confirmed for 'Kulvinder'; attempts=['open=pressed Search via AXPress', 'editable_field=missing', 'ope |
| 448 | fail | transition_attribution |  |
| 449 | ok | step | app=WhatsApp screenshot=True |
| 450 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 451 | ok | step | sources=['pyobjc_ax', 'macapptree'] agreement=0.7 |
| 452 | ok | observation |  |
| 453 | ok | observation |  |
| 454 | ok | forward_task |  |
| 455 | ok | world_patch | conversation |
| 456 | ok | fusion_conflicts |  |
| 457 | ok | goal_status |  |
| 458 | ok | decision_engine |  |
| 459 | ok | planner_decision |  |
| 460 | ok | execution | pressed Escape |
| 461 | ok | step | transition settle |
| 462 | ok | step | app=WhatsApp screenshot=True |
| 463 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 464 | ok | step | sources=['pyobjc_ax', 'macapptree'] agreement=0.7 |
| 465 | ok | observation |  |
| 466 | ok | step | transition poll |
| 467 | ok | step | app=WhatsApp screenshot=True |
| 468 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 469 | ok | step | sources=['pyobjc_ax', 'macapptree'] agreement=0.7 |
| 470 | ok | observation |  |
| 471 | ok | step | transition poll |
| 472 | ok | perception_retry |  |
| 473 | ok | step | perception retry (fusion_agreement_low) |
| 474 | ok | perception_retry_mode |  |
| 475 | ok | step | app=WhatsApp screenshot=True |
| 476 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 477 | ok | step | sources=['pyobjc_ax', 'macapptree'] agreement=0.7 |
| 478 | ok | observation |  |
| 479 | fail | perception_unsettled |  |
| 480 | ok | post_observation |  |
| 481 | ok | post_world_patch |  |
| 482 | fail | transition_eval |  |
| 483 | ok | transition_attribution |  |
| 484 | fail | verification |  |
| 485 | ok | step | app=WhatsApp screenshot=True |
| 486 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 487 | ok | step | sources=['pyobjc_ax', 'macapptree'] agreement=0.7 |
| 488 | ok | observation |  |
| 489 | ok | post_transition_richer_reobserve |  |
| 490 | fail | forward_predicate_rollback |  |
| 491 | ok | step | app=WhatsApp screenshot=True |
| 492 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 493 | ok | step | sources=['pyobjc_ax', 'macapptree'] agreement=0.7 |
| 494 | ok | observation |  |
| 495 | ok | observation |  |
| 496 | ok | forward_task |  |
| 497 | ok | world_patch | conversation |
| 498 | ok | fusion_conflicts |  |
| 499 | ok | goal_status |  |
| 500 | ok | decision_engine |  |
| 501 | ok | planner_decision |  |
| 502 | ok | execution | open Search via pressed Search via AXPress |
| 503 | ok | step | transition settle |
| 504 | ok | step | app=WhatsApp screenshot=True |
| 505 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 506 | ok | step | sources=['pyobjc_ax', 'macapptree'] agreement=0.7 |
| 507 | ok | observation |  |
| 508 | ok | step | transition poll |
| 509 | ok | step | app=WhatsApp screenshot=True |
| 510 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 511 | ok | step | sources=['pyobjc_ax', 'macapptree'] agreement=0.7 |
| 512 | ok | observation |  |
| 513 | ok | step | transition poll |
| 514 | ok | perception_retry |  |
| 515 | ok | step | perception retry (fusion_agreement_low) |
| 516 | ok | perception_retry_mode |  |
| 517 | ok | step | app=WhatsApp screenshot=True |
| 518 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 519 | ok | step | sources=['pyobjc_ax', 'macapptree'] agreement=0.7 |
| 520 | ok | observation |  |
| 521 | fail | perception_unsettled |  |
| 522 | ok | post_observation |  |
| 523 | ok | post_world_patch |  |
| 524 | fail | transition_eval |  |
| 525 | ok | transition_attribution |  |
| 526 | fail | verification |  |
| 527 | ok | step | app=WhatsApp screenshot=True |
| 528 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 529 | ok | step | sources=['pyobjc_ax', 'macapptree'] agreement=0.7 |
| 530 | ok | observation |  |
| 531 | ok | post_transition_richer_reobserve |  |
| 532 | fail | forward_predicate_rollback |  |
| 533 | ok | step | app=WhatsApp screenshot=True |
| 534 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 535 | ok | step | sources=['pyobjc_ax', 'macapptree'] agreement=0.7 |
| 536 | ok | observation |  |
| 537 | ok | observation |  |
| 538 | ok | forward_task |  |
| 539 | ok | world_patch | conversation |
| 540 | ok | fusion_conflicts |  |
| 541 | ok | goal_status |  |
| 542 | ok | decision_engine |  |
| 543 | ok | planner_decision |  |
| 544 | ok | step | re-perceive current world (actuation/world uncertainty) |
| 545 | ok | step | app=WhatsApp screenshot=True |
| 546 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 547 | ok | step | sources=['pyobjc_ax', 'macapptree'] agreement=0.7 |
| 548 | ok | observation |  |
| 549 | ok | observation |  |
| 550 | ok | forward_task |  |
| 551 | ok | world_patch | conversation |
| 552 | ok | fusion_conflicts |  |
| 553 | ok | goal_status |  |
| 554 | ok | decision_engine |  |
| 555 | ok | planner_decision |  |
| 556 | ok | execution | pressed Escape |
| 557 | ok | step | transition settle |
| 558 | ok | step | app=WhatsApp screenshot=True |
| 559 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 560 | ok | step | sources=['pyobjc_ax', 'macapptree'] agreement=0.7 |
| 561 | ok | observation |  |
| 562 | ok | step | transition poll |
| 563 | ok | step | app=WhatsApp screenshot=True |
| 564 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 565 | ok | step | sources=['pyobjc_ax', 'macapptree'] agreement=0.7 |
| 566 | ok | observation |  |
| 567 | ok | step | transition poll |
| 568 | ok | perception_retry |  |
| 569 | ok | step | perception retry (fusion_agreement_low) |
| 570 | ok | perception_retry_mode |  |
| 571 | ok | step | app=WhatsApp screenshot=True |
| 572 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 573 | ok | step | sources=['pyobjc_ax', 'macapptree'] agreement=0.7 |
| 574 | ok | observation |  |
| 575 | fail | perception_unsettled |  |
| 576 | ok | post_observation |  |
| 577 | ok | post_world_patch |  |
| 578 | fail | transition_eval |  |
| 579 | ok | transition_attribution |  |
| 580 | fail | verification |  |
| 581 | ok | step | app=WhatsApp screenshot=True |
| 582 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 583 | ok | step | sources=['pyobjc_ax', 'macapptree'] agreement=0.7 |
| 584 | ok | observation |  |
| 585 | ok | post_transition_richer_reobserve |  |
| 586 | fail | forward_predicate_rollback |  |
| 587 | ok | step | app=WhatsApp screenshot=True |
| 588 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 589 | ok | step | sources=['pyobjc_ax', 'macapptree'] agreement=0.7 |
| 590 | ok | observation |  |
| 591 | ok | observation |  |
| 592 | ok | forward_task |  |
| 593 | ok | world_patch | conversation |
| 594 | ok | fusion_conflicts |  |
| 595 | ok | goal_status |  |
| 596 | ok | decision_engine |  |
| 597 | ok | planner_decision |  |
| 598 | fail | execution | no editable field confirmed for 'Kulvinder'; attempts=['open=pressed Search via AXPress', 'editable_field=missing', 'ope |
| 599 | fail | transition_attribution |  |
| 600 | ok | step | app=WhatsApp screenshot=True |
| 601 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 602 | ok | step | sources=['pyobjc_ax', 'macapptree'] agreement=0.7 |
| 603 | ok | observation |  |
| 604 | ok | observation |  |
| 605 | ok | forward_task |  |
| 606 | ok | world_patch | conversation |
| 607 | ok | fusion_conflicts |  |
| 608 | ok | goal_status |  |
| 609 | ok | decision_engine |  |
| 610 | ok | planner_decision |  |
| 611 | ok | execution | open Search via pressed Search via AXPress |
| 612 | ok | step | transition settle |
| 613 | ok | step | app=WhatsApp screenshot=True |
| 614 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 615 | ok | step | sources=['pyobjc_ax', 'macapptree'] agreement=0.7 |
| 616 | ok | observation |  |
| 617 | ok | step | transition poll |
| 618 | ok | step | app=WhatsApp screenshot=True |
| 619 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 620 | ok | step | sources=['pyobjc_ax', 'macapptree'] agreement=0.7 |
| 621 | ok | observation |  |
| 622 | ok | step | transition poll |
| 623 | ok | perception_retry |  |
| 624 | ok | step | perception retry (fusion_agreement_low) |
| 625 | ok | perception_retry_mode |  |
| 626 | ok | step | app=WhatsApp screenshot=True |
| 627 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 628 | ok | step | sources=['pyobjc_ax', 'macapptree'] agreement=0.7 |
| 629 | ok | observation |  |
| 630 | fail | perception_unsettled |  |
| 631 | ok | post_observation |  |
| 632 | ok | post_world_patch |  |
| 633 | fail | transition_eval |  |
| 634 | ok | transition_attribution |  |
| 635 | fail | verification |  |
| 636 | ok | step | app=WhatsApp screenshot=True |
| 637 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 638 | ok | step | sources=['pyobjc_ax', 'macapptree'] agreement=0.7 |
| 639 | ok | observation |  |
| 640 | ok | post_transition_richer_reobserve |  |
| 641 | fail | forward_predicate_rollback |  |
| 642 | ok | step | app=WhatsApp screenshot=True |
| 643 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 644 | ok | step | sources=['pyobjc_ax', 'macapptree'] agreement=0.7 |
| 645 | ok | observation |  |
| 646 | ok | observation |  |
| 647 | ok | forward_task |  |
| 648 | ok | world_patch | conversation |
| 649 | ok | fusion_conflicts |  |
| 650 | ok | goal_status |  |
| 651 | ok | decision_engine |  |
| 652 | ok | planner_decision |  |
| 653 | ok | execution | pressed Escape |
| 654 | ok | step | transition settle |
| 655 | ok | step | app=WhatsApp screenshot=True |
| 656 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 657 | ok | step | sources=['pyobjc_ax', 'macapptree'] agreement=0.7 |
| 658 | ok | observation |  |
| 659 | ok | step | transition poll |
| 660 | ok | step | app=WhatsApp screenshot=True |
| 661 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 662 | ok | step | sources=['pyobjc_ax', 'macapptree'] agreement=0.7 |
| 663 | ok | observation |  |
| 664 | ok | step | transition poll |
| 665 | ok | perception_retry |  |
| 666 | ok | step | perception retry (fusion_agreement_low) |
| 667 | ok | perception_retry_mode |  |
| 668 | ok | step | app=WhatsApp screenshot=True |
| 669 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 670 | ok | step | sources=['pyobjc_ax', 'macapptree'] agreement=0.7 |
| 671 | ok | observation |  |
| 672 | fail | perception_unsettled |  |
| 673 | ok | post_observation |  |
| 674 | ok | post_world_patch |  |
| 675 | fail | transition_eval |  |
| 676 | ok | transition_attribution |  |
| 677 | fail | verification |  |
| 678 | ok | step | app=WhatsApp screenshot=True |
| 679 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 680 | ok | step | sources=['pyobjc_ax', 'macapptree'] agreement=0.7 |
| 681 | ok | observation |  |
| 682 | ok | post_transition_richer_reobserve |  |
| 683 | fail | forward_predicate_rollback |  |
| 684 | ok | step | app=WhatsApp screenshot=True |
| 685 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 686 | ok | step | sources=['pyobjc_ax', 'macapptree'] agreement=0.7 |
| 687 | ok | observation |  |
| 688 | ok | observation |  |
| 689 | ok | forward_task |  |
| 690 | ok | world_patch | conversation |
| 691 | ok | fusion_conflicts |  |
| 692 | ok | goal_status |  |
| 693 | ok | decision_engine |  |
| 694 | ok | planner_decision |  |
| 695 | ok | step | re-perceive current world (actuation/world uncertainty) |
| 696 | ok | step | app=WhatsApp screenshot=True |
| 697 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 698 | ok | step | sources=['pyobjc_ax', 'macapptree'] agreement=0.7 |
| 699 | ok | observation |  |
| 700 | ok | observation |  |
| 701 | ok | forward_task |  |
| 702 | ok | world_patch | conversation |
| 703 | ok | fusion_conflicts |  |
| 704 | ok | goal_status |  |
| 705 | ok | decision_engine |  |
| 706 | ok | planner_decision |  |
| 707 | fail | execution | no editable field confirmed for 'Kulvinder'; attempts=['open=pressed Search via AXPress', 'editable_field=missing', 'ope |
| 708 | fail | transition_attribution |  |
| 709 | ok | step | app=WhatsApp screenshot=True |
| 710 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 711 | ok | step | sources=['pyobjc_ax', 'macapptree'] agreement=0.7 |
| 712 | ok | observation |  |
| 713 | ok | observation |  |
| 714 | ok | forward_task |  |
| 715 | ok | world_patch | conversation |
| 716 | ok | fusion_conflicts |  |
| 717 | ok | goal_status |  |
| 718 | ok | decision_engine |  |
| 719 | ok | planner_decision |  |
| 720 | ok | execution | pressed Escape |
| 721 | ok | step | transition settle |
| 722 | ok | step | app=WhatsApp screenshot=True |
| 723 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 724 | ok | step | sources=['pyobjc_ax', 'macapptree'] agreement=0.7 |
| 725 | ok | observation |  |
| 726 | ok | step | transition poll |
| 727 | ok | step | app=WhatsApp screenshot=True |
| 728 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 729 | ok | step | sources=['pyobjc_ax', 'macapptree'] agreement=0.7 |
| 730 | ok | observation |  |
| 731 | ok | step | transition poll |
| 732 | ok | perception_retry |  |
| 733 | ok | step | perception retry (fusion_agreement_low) |
| 734 | ok | perception_retry_mode |  |
| 735 | ok | step | app=WhatsApp screenshot=True |
| 736 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 737 | ok | step | sources=['pyobjc_ax', 'macapptree'] agreement=0.7 |
| 738 | ok | observation |  |
| 739 | fail | perception_unsettled |  |
| 740 | ok | post_observation |  |
| 741 | ok | post_world_patch |  |
| 742 | fail | transition_eval |  |
| 743 | ok | transition_attribution |  |
| 744 | fail | verification |  |
| 745 | ok | step | app=WhatsApp screenshot=True |
| 746 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 747 | ok | step | sources=['pyobjc_ax', 'macapptree'] agreement=0.7 |
| 748 | ok | observation |  |
| 749 | ok | post_transition_richer_reobserve |  |
| 750 | fail | forward_predicate_rollback |  |
| 751 | ok | step | app=WhatsApp screenshot=True |
| 752 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 753 | ok | step | sources=['pyobjc_ax', 'macapptree'] agreement=0.7 |
| 754 | ok | observation |  |
| 755 | ok | observation |  |
| 756 | ok | forward_task |  |
| 757 | ok | world_patch | conversation |
| 758 | ok | fusion_conflicts |  |
| 759 | ok | goal_status |  |
| 760 | ok | decision_engine |  |
| 761 | ok | planner_decision |  |
| 762 | ok | execution | open Search via pressed Search via AXPress |
| 763 | ok | step | transition settle |
| 764 | ok | step | app=WhatsApp screenshot=True |
| 765 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 766 | ok | step | sources=['pyobjc_ax', 'macapptree'] agreement=0.7 |
| 767 | ok | observation |  |
| 768 | ok | step | transition poll |
| 769 | ok | step | app=WhatsApp screenshot=True |
| 770 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 771 | ok | step | sources=['pyobjc_ax', 'macapptree'] agreement=0.7 |
| 772 | ok | observation |  |
| 773 | ok | step | transition poll |
| 774 | ok | perception_retry |  |
| 775 | ok | step | perception retry (fusion_agreement_low) |
| 776 | ok | perception_retry_mode |  |
| 777 | ok | step | app=WhatsApp screenshot=True |
| 778 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 779 | ok | step | sources=['pyobjc_ax', 'macapptree'] agreement=0.7 |
| 780 | ok | observation |  |
| 781 | fail | perception_unsettled |  |
| 782 | ok | post_observation |  |
| 783 | ok | post_world_patch |  |
| 784 | fail | transition_eval |  |
| 785 | ok | transition_attribution |  |
| 786 | fail | verification |  |
| 787 | ok | step | app=WhatsApp screenshot=True |
| 788 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 789 | ok | step | sources=['pyobjc_ax', 'macapptree'] agreement=0.7 |
| 790 | ok | observation |  |
| 791 | ok | post_transition_richer_reobserve |  |
| 792 | fail | forward_predicate_rollback |  |
| 793 | ok | step | app=WhatsApp screenshot=True |
| 794 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 795 | ok | step | sources=['pyobjc_ax', 'macapptree'] agreement=0.7 |
| 796 | ok | observation |  |
| 797 | ok | observation |  |
| 798 | ok | forward_task |  |
| 799 | ok | world_patch | conversation |
| 800 | ok | fusion_conflicts |  |
| 801 | ok | goal_status |  |
| 802 | ok | decision_engine |  |
| 803 | ok | planner_decision |  |
| 804 | ok | step | re-perceive current world (actuation/world uncertainty) |
| 805 | ok | step | app=WhatsApp screenshot=True |
| 806 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 807 | ok | step | sources=['pyobjc_ax', 'macapptree'] agreement=0.7 |
| 808 | ok | observation |  |
| 809 | ok | observation |  |
| 810 | ok | forward_task |  |
| 811 | ok | world_patch | conversation |
| 812 | ok | fusion_conflicts |  |
| 813 | ok | goal_status |  |
| 814 | ok | decision_engine |  |
| 815 | ok | planner_decision |  |
| 816 | ok | execution | pressed Escape |
| 817 | ok | step | transition settle |
| 818 | ok | step | app=WhatsApp screenshot=True |
| 819 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 820 | ok | step | sources=['pyobjc_ax', 'macapptree'] agreement=0.7 |
| 821 | ok | observation |  |
| 822 | ok | step | transition poll |
| 823 | ok | step | app=WhatsApp screenshot=True |
| 824 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 825 | ok | step | sources=['pyobjc_ax', 'macapptree'] agreement=0.7 |
| 826 | ok | observation |  |
| 827 | ok | step | transition poll |
| 828 | ok | perception_retry |  |
| 829 | ok | step | perception retry (fusion_agreement_low) |
| 830 | ok | perception_retry_mode |  |
| 831 | ok | step | app=WhatsApp screenshot=True |
| 832 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 833 | ok | step | sources=['pyobjc_ax', 'macapptree'] agreement=0.7 |
| 834 | ok | observation |  |
| 835 | fail | perception_unsettled |  |
| 836 | ok | post_observation |  |
| 837 | ok | post_world_patch |  |
| 838 | fail | transition_eval |  |
| 839 | ok | transition_attribution |  |
| 840 | fail | verification |  |
| 841 | ok | step | app=WhatsApp screenshot=True |
| 842 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 843 | ok | step | sources=['pyobjc_ax', 'macapptree'] agreement=0.7 |
| 844 | ok | observation |  |
| 845 | ok | post_transition_richer_reobserve |  |
| 846 | fail | forward_predicate_rollback |  |
| 847 | ok | step | app=WhatsApp screenshot=True |
| 848 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 849 | ok | step | sources=['pyobjc_ax', 'macapptree'] agreement=0.7 |
| 850 | ok | observation |  |
| 851 | ok | observation |  |
| 852 | ok | forward_task |  |
| 853 | ok | world_patch | conversation |
| 854 | ok | fusion_conflicts |  |
| 855 | ok | goal_status |  |
| 856 | ok | decision_engine |  |
| 857 | ok | planner_decision |  |
| 858 | fail | execution | no editable field confirmed for 'Kulvinder'; attempts=['open=pressed Search via AXPress', 'editable_field=missing', 'ope |
| 859 | fail | transition_attribution |  |
| 860 | ok | step | app=WhatsApp screenshot=True |
| 861 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 862 | ok | step | sources=['pyobjc_ax', 'macapptree'] agreement=0.7 |
| 863 | ok | observation |  |
| 864 | ok | observation |  |
| 865 | ok | forward_task |  |
| 866 | ok | world_patch | conversation |
| 867 | ok | fusion_conflicts |  |
| 868 | ok | goal_status |  |
| 869 | ok | decision_engine |  |
| 870 | ok | planner_decision |  |
| 871 | ok | execution | open Search via pressed Search via AXPress |
| 872 | ok | step | transition settle |
| 873 | ok | step | app=WhatsApp screenshot=True |
| 874 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 875 | ok | step | sources=['pyobjc_ax', 'macapptree'] agreement=0.7 |
| 876 | ok | observation |  |
| 877 | ok | step | transition poll |
| 878 | ok | step | app=WhatsApp screenshot=True |
| 879 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 880 | ok | step | sources=['pyobjc_ax', 'macapptree'] agreement=0.7 |
| 881 | ok | observation |  |
| 882 | ok | step | transition poll |
| 883 | ok | perception_retry |  |
| 884 | ok | step | perception retry (fusion_agreement_low) |
| 885 | ok | perception_retry_mode |  |
| 886 | ok | step | app=WhatsApp screenshot=True |
| 887 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 888 | ok | step | sources=['pyobjc_ax', 'macapptree'] agreement=0.7 |
| 889 | ok | observation |  |
| 890 | fail | perception_unsettled |  |
| 891 | ok | post_observation |  |
| 892 | ok | post_world_patch |  |
| 893 | fail | transition_eval |  |
| 894 | ok | transition_attribution |  |
| 895 | fail | verification |  |
| 896 | ok | step | app=WhatsApp screenshot=True |
| 897 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 898 | ok | step | sources=['pyobjc_ax', 'macapptree'] agreement=0.7 |
| 899 | ok | observation |  |
| 900 | ok | post_transition_richer_reobserve |  |
| 901 | fail | forward_predicate_rollback |  |
| 902 | ok | step | app=WhatsApp screenshot=True |
| 903 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 904 | ok | step | sources=['pyobjc_ax', 'macapptree'] agreement=0.7 |
| 905 | ok | observation |  |
| 906 | ok | observation |  |
| 907 | ok | forward_task |  |
| 908 | ok | world_patch | conversation |
| 909 | ok | fusion_conflicts |  |
| 910 | ok | goal_status |  |
| 911 | ok | decision_engine |  |
| 912 | ok | planner_decision |  |
| 913 | ok | execution | pressed Escape |
| 914 | ok | step | transition settle |
| 915 | ok | step | app=WhatsApp screenshot=True |
| 916 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 917 | ok | step | sources=['pyobjc_ax', 'macapptree'] agreement=0.7 |
| 918 | ok | observation |  |
| 919 | ok | step | transition poll |
| 920 | ok | step | app=WhatsApp screenshot=True |
| 921 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 922 | ok | step | sources=['pyobjc_ax', 'macapptree'] agreement=0.7 |
| 923 | ok | observation |  |
| 924 | ok | step | transition poll |
| 925 | ok | perception_retry |  |
| 926 | ok | step | perception retry (fusion_agreement_low) |
| 927 | ok | perception_retry_mode |  |
| 928 | ok | step | app=WhatsApp screenshot=True |
| 929 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 930 | ok | step | sources=['pyobjc_ax', 'macapptree'] agreement=0.7 |
| 931 | ok | observation |  |
| 932 | fail | perception_unsettled |  |
| 933 | ok | post_observation |  |
| 934 | ok | post_world_patch |  |
| 935 | fail | transition_eval |  |
| 936 | ok | transition_attribution |  |
| 937 | fail | verification |  |
| 938 | ok | step | app=WhatsApp screenshot=True |
| 939 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 940 | ok | step | sources=['pyobjc_ax', 'macapptree'] agreement=0.7 |
| 941 | ok | observation |  |
| 942 | ok | post_transition_richer_reobserve |  |
| 943 | fail | forward_predicate_rollback |  |
| 944 | ok | step | app=WhatsApp screenshot=True |
| 945 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 946 | ok | step | sources=['pyobjc_ax', 'macapptree'] agreement=0.7 |
| 947 | ok | observation |  |
| 948 | ok | observation |  |
| 949 | ok | forward_task |  |
| 950 | ok | world_patch | conversation |
| 951 | ok | fusion_conflicts |  |
| 952 | ok | goal_status |  |
| 953 | ok | decision_engine |  |
| 954 | ok | planner_decision |  |
| 955 | ok | step | re-perceive current world (actuation/world uncertainty) |
| 956 | ok | step | app=WhatsApp screenshot=True |
| 957 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 958 | ok | step | sources=['pyobjc_ax', 'macapptree'] agreement=0.7 |
| 959 | ok | observation |  |
| 960 | ok | observation |  |
| 961 | ok | forward_task |  |
| 962 | ok | world_patch | conversation |
| 963 | ok | fusion_conflicts |  |
| 964 | ok | goal_status |  |
| 965 | ok | decision_engine |  |
| 966 | ok | planner_decision |  |
| 967 | fail | execution | no editable field confirmed for 'Kulvinder'; attempts=['open=pressed Search via AXPress', 'editable_field=missing', 'ope |
| 968 | fail | transition_attribution |  |
| 969 | ok | step | app=WhatsApp screenshot=True |
| 970 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 971 | ok | step | sources=['pyobjc_ax', 'macapptree'] agreement=0.7 |
| 972 | ok | observation |  |
| 973 | ok | observation |  |
| 974 | ok | forward_task |  |
| 975 | ok | world_patch | conversation |
| 976 | ok | fusion_conflicts |  |
| 977 | ok | goal_status |  |
| 978 | ok | decision_engine |  |
| 979 | ok | planner_decision |  |
| 980 | ok | execution | pressed Escape |
| 981 | ok | step | transition settle |
| 982 | ok | step | app=WhatsApp screenshot=True |
| 983 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 984 | ok | step | sources=['pyobjc_ax', 'macapptree'] agreement=0.7 |
| 985 | ok | observation |  |
| 986 | ok | step | transition poll |
| 987 | ok | step | app=WhatsApp screenshot=True |
| 988 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 989 | ok | step | sources=['pyobjc_ax', 'macapptree'] agreement=0.7 |
| 990 | ok | observation |  |
| 991 | ok | step | transition poll |
| 992 | ok | perception_retry |  |
| 993 | ok | step | perception retry (fusion_agreement_low) |
| 994 | ok | perception_retry_mode |  |
| 995 | ok | step | app=WhatsApp screenshot=True |
| 996 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 997 | ok | step | sources=['pyobjc_ax', 'macapptree'] agreement=0.7 |
| 998 | ok | observation |  |
| 999 | fail | perception_unsettled |  |
| 1000 | ok | post_observation |  |
| 1001 | ok | post_world_patch |  |
| 1002 | fail | transition_eval |  |
| 1003 | ok | transition_attribution |  |
| 1004 | fail | verification |  |
| 1005 | ok | step | app=WhatsApp screenshot=True |
| 1006 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1007 | ok | step | sources=['pyobjc_ax', 'macapptree'] agreement=0.7 |
| 1008 | ok | observation |  |
| 1009 | ok | post_transition_richer_reobserve |  |
| 1010 | fail | forward_predicate_rollback |  |
| 1011 | ok | step | app=WhatsApp screenshot=True |
| 1012 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1013 | ok | step | sources=['pyobjc_ax', 'macapptree'] agreement=0.7 |
| 1014 | ok | observation |  |
| 1015 | ok | observation |  |
| 1016 | ok | forward_task |  |
| 1017 | ok | world_patch | conversation |
| 1018 | ok | fusion_conflicts |  |
| 1019 | ok | goal_status |  |
| 1020 | ok | decision_engine |  |
| 1021 | ok | planner_decision |  |
| 1022 | ok | execution | open Search via pressed Search via AXPress |
| 1023 | ok | step | transition settle |
| 1024 | ok | step | app=WhatsApp screenshot=True |
| 1025 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1026 | ok | step | sources=['pyobjc_ax', 'macapptree'] agreement=0.7 |
| 1027 | ok | observation |  |
| 1028 | ok | step | transition poll |
| 1029 | ok | step | app=WhatsApp screenshot=True |
| 1030 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1031 | ok | step | sources=['pyobjc_ax', 'macapptree'] agreement=0.7 |
| 1032 | ok | observation |  |
| 1033 | ok | step | transition poll |
| 1034 | ok | perception_retry |  |
| 1035 | ok | step | perception retry (fusion_agreement_low) |
| 1036 | ok | perception_retry_mode |  |
| 1037 | ok | step | app=WhatsApp screenshot=True |
| 1038 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1039 | ok | step | sources=['pyobjc_ax', 'macapptree'] agreement=0.7 |
| 1040 | ok | observation |  |
| 1041 | fail | perception_unsettled |  |
| 1042 | ok | post_observation |  |
| 1043 | ok | post_world_patch |  |
| 1044 | fail | transition_eval |  |
| 1045 | ok | transition_attribution |  |
| 1046 | fail | verification |  |
| 1047 | ok | step | app=WhatsApp screenshot=True |
| 1048 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1049 | ok | step | sources=['pyobjc_ax', 'macapptree'] agreement=0.7 |
| 1050 | ok | observation |  |
| 1051 | ok | post_transition_richer_reobserve |  |
| 1052 | fail | forward_predicate_rollback |  |
| 1053 | ok | step | app=WhatsApp screenshot=True |
| 1054 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1055 | ok | step | sources=['pyobjc_ax', 'macapptree'] agreement=0.7 |
| 1056 | ok | observation |  |
| 1057 | ok | observation |  |
| 1058 | ok | forward_task |  |
| 1059 | ok | world_patch | conversation |
| 1060 | ok | fusion_conflicts |  |
| 1061 | ok | goal_status |  |
| 1062 | ok | decision_engine |  |
| 1063 | ok | planner_decision |  |
| 1064 | ok | step | re-perceive current world (actuation/world uncertainty) |
| 1065 | ok | step | app=WhatsApp screenshot=True |
| 1066 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1067 | ok | step | sources=['pyobjc_ax', 'macapptree'] agreement=0.7 |
| 1068 | ok | observation |  |
| 1069 | ok | observation |  |
| 1070 | ok | forward_task |  |
| 1071 | ok | world_patch | conversation |
| 1072 | ok | fusion_conflicts |  |
| 1073 | ok | goal_status |  |
| 1074 | ok | decision_engine |  |
| 1075 | ok | planner_decision |  |
| 1076 | ok | execution | pressed Escape |
| 1077 | ok | step | transition settle |
| 1078 | ok | step | app=WhatsApp screenshot=True |
| 1079 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1080 | ok | step | sources=['pyobjc_ax', 'macapptree'] agreement=0.7 |
| 1081 | ok | observation |  |
| 1082 | ok | step | transition poll |
| 1083 | ok | step | app=WhatsApp screenshot=True |
| 1084 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1085 | ok | step | sources=['pyobjc_ax', 'macapptree'] agreement=0.7 |
| 1086 | ok | observation |  |
| 1087 | ok | step | transition poll |
| 1088 | ok | perception_retry |  |
| 1089 | ok | step | perception retry (fusion_agreement_low) |
| 1090 | ok | perception_retry_mode |  |
| 1091 | ok | step | app=WhatsApp screenshot=True |
| 1092 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1093 | ok | step | sources=['pyobjc_ax', 'macapptree'] agreement=0.7 |
| 1094 | ok | observation |  |
| 1095 | fail | perception_unsettled |  |
| 1096 | ok | post_observation |  |
| 1097 | ok | post_world_patch |  |
| 1098 | fail | transition_eval |  |
| 1099 | ok | transition_attribution |  |
| 1100 | fail | verification |  |
| 1101 | ok | step | app=WhatsApp screenshot=True |
| 1102 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1103 | ok | step | sources=['pyobjc_ax', 'macapptree'] agreement=0.7 |
| 1104 | ok | observation |  |
| 1105 | ok | post_transition_richer_reobserve |  |
| 1106 | fail | forward_predicate_rollback |  |
| 1107 | ok | step | app=WhatsApp screenshot=True |
| 1108 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1109 | ok | step | sources=['pyobjc_ax', 'macapptree'] agreement=0.7 |
| 1110 | ok | observation |  |
| 1111 | ok | observation |  |
| 1112 | ok | forward_task |  |
| 1113 | ok | world_patch | conversation |
| 1114 | ok | fusion_conflicts |  |
| 1115 | ok | goal_status |  |
| 1116 | ok | decision_engine |  |
| 1117 | ok | planner_decision |  |
| 1118 | fail | execution | no editable field confirmed for 'Kulvinder'; attempts=['open=pressed Search via AXPress', 'editable_field=missing', 'ope |
| 1119 | fail | transition_attribution |  |
| 1120 | ok | step | app=WhatsApp screenshot=True |
| 1121 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1122 | ok | step | sources=['pyobjc_ax', 'macapptree'] agreement=0.7 |
| 1123 | ok | observation |  |
| 1124 | ok | observation |  |
| 1125 | ok | forward_task |  |
| 1126 | ok | world_patch | conversation |
| 1127 | ok | fusion_conflicts |  |
| 1128 | ok | goal_status |  |
| 1129 | ok | decision_engine |  |
| 1130 | ok | planner_decision |  |
| 1131 | ok | execution | open Search via pressed Search via AXPress |
| 1132 | ok | step | transition settle |
| 1133 | ok | step | app=WhatsApp screenshot=True |
| 1134 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1135 | ok | step | sources=['pyobjc_ax', 'macapptree'] agreement=0.7 |
| 1136 | ok | observation |  |
| 1137 | ok | step | transition poll |
| 1138 | ok | step | app=WhatsApp screenshot=True |
| 1139 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1140 | ok | step | sources=['pyobjc_ax', 'macapptree'] agreement=0.7 |
| 1141 | ok | observation |  |
| 1142 | ok | step | transition poll |
| 1143 | ok | perception_retry |  |
| 1144 | ok | step | perception retry (fusion_agreement_low) |
| 1145 | ok | perception_retry_mode |  |
| 1146 | ok | step | app=WhatsApp screenshot=True |
| 1147 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1148 | ok | step | sources=['pyobjc_ax', 'macapptree'] agreement=0.7 |
| 1149 | ok | observation |  |
| 1150 | fail | perception_unsettled |  |
| 1151 | ok | post_observation |  |
| 1152 | ok | post_world_patch |  |
| 1153 | fail | transition_eval |  |
| 1154 | ok | transition_attribution |  |
| 1155 | fail | verification |  |
| 1156 | ok | step | app=WhatsApp screenshot=True |
| 1157 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1158 | ok | step | sources=['pyobjc_ax', 'macapptree'] agreement=0.7 |
| 1159 | ok | observation |  |
| 1160 | ok | post_transition_richer_reobserve |  |
| 1161 | fail | forward_predicate_rollback |  |
| 1162 | ok | step | app=WhatsApp screenshot=True |
| 1163 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1164 | ok | step | sources=['pyobjc_ax', 'macapptree'] agreement=0.7 |
| 1165 | ok | observation |  |
| 1166 | ok | observation |  |
| 1167 | ok | forward_task |  |
| 1168 | ok | world_patch | conversation |
| 1169 | ok | fusion_conflicts |  |
| 1170 | ok | goal_status |  |
| 1171 | ok | decision_engine |  |
| 1172 | ok | planner_decision |  |
| 1173 | ok | execution | pressed Escape |
| 1174 | ok | step | transition settle |
| 1175 | ok | step | app=WhatsApp screenshot=True |
| 1176 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1177 | ok | step | sources=['pyobjc_ax', 'macapptree'] agreement=0.7 |
| 1178 | ok | observation |  |
| 1179 | ok | step | transition poll |
| 1180 | ok | step | app=WhatsApp screenshot=True |
| 1181 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1182 | ok | step | sources=['pyobjc_ax', 'macapptree'] agreement=0.7 |
| 1183 | ok | observation |  |
| 1184 | ok | step | transition poll |
| 1185 | ok | perception_retry |  |
| 1186 | ok | step | perception retry (fusion_agreement_low) |
| 1187 | ok | perception_retry_mode |  |
| 1188 | ok | step | app=WhatsApp screenshot=True |
| 1189 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1190 | ok | step | sources=['pyobjc_ax', 'macapptree'] agreement=0.7 |
| 1191 | ok | observation |  |
| 1192 | fail | perception_unsettled |  |
| 1193 | ok | post_observation |  |
| 1194 | ok | post_world_patch |  |
| 1195 | fail | transition_eval |  |
| 1196 | ok | transition_attribution |  |
| 1197 | fail | verification |  |
| 1198 | ok | step | app=WhatsApp screenshot=True |
| 1199 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1200 | ok | step | sources=['pyobjc_ax', 'macapptree'] agreement=0.7 |
| 1201 | ok | observation |  |
| 1202 | ok | post_transition_richer_reobserve |  |
| 1203 | fail | forward_predicate_rollback |  |
| 1204 | ok | step | app=WhatsApp screenshot=True |
| 1205 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1206 | ok | step | sources=['pyobjc_ax', 'macapptree'] agreement=0.7 |
| 1207 | ok | observation |  |
| 1208 | ok | observation |  |
| 1209 | ok | forward_task |  |
| 1210 | ok | world_patch | conversation |
| 1211 | ok | fusion_conflicts |  |
| 1212 | ok | goal_status |  |
| 1213 | ok | decision_engine |  |
| 1214 | ok | planner_decision |  |
| 1215 | ok | step | re-perceive current world (actuation/world uncertainty) |
| 1216 | ok | step | app=WhatsApp screenshot=True |
| 1217 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1218 | ok | step | sources=['pyobjc_ax', 'macapptree'] agreement=0.7 |
| 1219 | ok | observation |  |
| 1220 | ok | observation |  |
| 1221 | ok | forward_task |  |
| 1222 | ok | world_patch | conversation |
| 1223 | ok | fusion_conflicts |  |
| 1224 | ok | goal_status |  |
| 1225 | ok | decision_engine |  |
| 1226 | ok | planner_decision |  |
| 1227 | fail | execution | no editable field confirmed for 'Kulvinder'; attempts=['open=pressed Search via AXPress', 'editable_field=missing', 'ope |
| 1228 | fail | transition_attribution |  |
| 1229 | ok | step | app=WhatsApp screenshot=True |
| 1230 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1231 | ok | step | sources=['pyobjc_ax', 'macapptree'] agreement=0.7 |
| 1232 | ok | observation |  |
| 1233 | ok | observation |  |
| 1234 | ok | forward_task |  |
| 1235 | ok | world_patch | conversation |
| 1236 | ok | fusion_conflicts |  |
| 1237 | ok | goal_status |  |
| 1238 | ok | decision_engine |  |
| 1239 | ok | planner_decision |  |
| 1240 | ok | execution | pressed Escape |
| 1241 | ok | step | transition settle |
| 1242 | ok | step | app=WhatsApp screenshot=True |
| 1243 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1244 | ok | step | sources=['pyobjc_ax', 'macapptree'] agreement=0.7 |
| 1245 | ok | observation |  |
| 1246 | ok | step | transition poll |
| 1247 | ok | step | app=WhatsApp screenshot=True |
| 1248 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1249 | ok | step | sources=['pyobjc_ax', 'macapptree'] agreement=0.7 |
| 1250 | ok | observation |  |
| 1251 | ok | step | transition poll |
| 1252 | ok | perception_retry |  |
| 1253 | ok | step | perception retry (fusion_agreement_low) |
| 1254 | ok | perception_retry_mode |  |
| 1255 | ok | step | app=WhatsApp screenshot=True |
| 1256 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1257 | ok | step | sources=['pyobjc_ax', 'macapptree'] agreement=0.7 |
| 1258 | ok | observation |  |
| 1259 | fail | perception_unsettled |  |
| 1260 | ok | post_observation |  |
| 1261 | ok | post_world_patch |  |
| 1262 | fail | transition_eval |  |
| 1263 | ok | transition_attribution |  |
| 1264 | fail | verification |  |
| 1265 | ok | step | app=WhatsApp screenshot=True |
| 1266 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1267 | ok | step | sources=['pyobjc_ax', 'macapptree'] agreement=0.7 |
| 1268 | ok | observation |  |
| 1269 | ok | post_transition_richer_reobserve |  |
| 1270 | fail | forward_predicate_rollback |  |
| 1271 | ok | step | app=WhatsApp screenshot=True |
| 1272 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1273 | ok | step | sources=['pyobjc_ax', 'macapptree'] agreement=0.7 |
| 1274 | ok | observation |  |
| 1275 | ok | observation |  |
| 1276 | ok | forward_task |  |
| 1277 | ok | world_patch | conversation |
| 1278 | ok | fusion_conflicts |  |
| 1279 | ok | goal_status |  |
| 1280 | ok | decision_engine |  |
| 1281 | ok | planner_decision |  |
| 1282 | ok | execution | open Search via pressed Search via AXPress |
| 1283 | ok | step | transition settle |
| 1284 | ok | step | app=WhatsApp screenshot=True |
| 1285 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1286 | ok | step | sources=['pyobjc_ax', 'macapptree'] agreement=0.7 |
| 1287 | ok | observation |  |
| 1288 | ok | step | transition poll |
| 1289 | ok | step | app=WhatsApp screenshot=True |
| 1290 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1291 | ok | step | sources=['pyobjc_ax', 'macapptree'] agreement=0.7 |
| 1292 | ok | observation |  |
| 1293 | ok | step | transition poll |
| 1294 | ok | perception_retry |  |
| 1295 | ok | step | perception retry (fusion_agreement_low) |
| 1296 | ok | perception_retry_mode |  |
| 1297 | ok | step | app=WhatsApp screenshot=True |
| 1298 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1299 | ok | step | sources=['pyobjc_ax', 'macapptree'] agreement=0.7 |
| 1300 | ok | observation |  |
| 1301 | fail | perception_unsettled |  |
| 1302 | ok | post_observation |  |
| 1303 | ok | post_world_patch |  |
| 1304 | fail | transition_eval |  |
| 1305 | ok | transition_attribution |  |
| 1306 | fail | verification |  |
| 1307 | ok | step | app=WhatsApp screenshot=True |
| 1308 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1309 | ok | step | sources=['pyobjc_ax', 'macapptree'] agreement=0.7 |
| 1310 | ok | observation |  |
| 1311 | ok | post_transition_richer_reobserve |  |
| 1312 | fail | forward_predicate_rollback |  |
| 1313 | ok | step | app=WhatsApp screenshot=True |
| 1314 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1315 | ok | step | sources=['pyobjc_ax', 'macapptree'] agreement=0.7 |
| 1316 | ok | observation |  |
| 1317 | ok | observation |  |
| 1318 | ok | forward_task |  |
| 1319 | ok | world_patch | conversation |
| 1320 | ok | fusion_conflicts |  |
| 1321 | ok | goal_status |  |
| 1322 | ok | decision_engine |  |
| 1323 | ok | planner_decision |  |
| 1324 | ok | step | re-perceive current world (actuation/world uncertainty) |
| 1325 | ok | step | app=WhatsApp screenshot=True |
| 1326 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1327 | ok | step | sources=['pyobjc_ax', 'macapptree'] agreement=0.7 |
| 1328 | ok | observation |  |
| 1329 | ok | observation |  |
| 1330 | ok | forward_task |  |
| 1331 | ok | world_patch | conversation |
| 1332 | ok | fusion_conflicts |  |
| 1333 | ok | goal_status |  |
| 1334 | ok | decision_engine |  |
| 1335 | ok | planner_decision |  |
| 1336 | ok | execution | pressed Escape |
| 1337 | ok | step | transition settle |
| 1338 | ok | step | app=WhatsApp screenshot=True |
| 1339 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1340 | ok | step | sources=['pyobjc_ax', 'macapptree'] agreement=0.7 |
| 1341 | ok | observation |  |
| 1342 | ok | step | transition poll |
| 1343 | ok | step | app=WhatsApp screenshot=True |
| 1344 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1345 | ok | step | sources=['pyobjc_ax', 'macapptree'] agreement=0.7 |
| 1346 | ok | observation |  |
| 1347 | ok | step | transition poll |
| 1348 | ok | perception_retry |  |
| 1349 | ok | step | perception retry (fusion_agreement_low) |
| 1350 | ok | perception_retry_mode |  |
| 1351 | ok | step | app=WhatsApp screenshot=True |
| 1352 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1353 | ok | step | sources=['pyobjc_ax', 'macapptree'] agreement=0.7 |
| 1354 | ok | observation |  |
| 1355 | fail | perception_unsettled |  |
| 1356 | ok | post_observation |  |
| 1357 | ok | post_world_patch |  |
| 1358 | fail | transition_eval |  |
| 1359 | ok | transition_attribution |  |
| 1360 | fail | verification |  |
| 1361 | ok | step | app=WhatsApp screenshot=True |
| 1362 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1363 | ok | step | sources=['pyobjc_ax', 'macapptree'] agreement=0.7 |
| 1364 | ok | observation |  |
| 1365 | ok | post_transition_richer_reobserve |  |
| 1366 | fail | forward_predicate_rollback |  |
| 1367 | ok | step | app=WhatsApp screenshot=True |
| 1368 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1369 | ok | step | sources=['pyobjc_ax', 'macapptree'] agreement=0.7 |
| 1370 | ok | observation |  |
| 1371 | ok | observation |  |
| 1372 | ok | forward_task |  |
| 1373 | ok | world_patch | conversation |
| 1374 | ok | fusion_conflicts |  |
| 1375 | ok | goal_status |  |
| 1376 | ok | decision_engine |  |
| 1377 | ok | planner_decision |  |
| 1378 | fail | execution | no editable field confirmed for 'Kulvinder'; attempts=['open=pressed Search via AXPress', 'editable_field=missing', 'ope |
| 1379 | fail | transition_attribution |  |
| 1380 | ok | step | app=WhatsApp screenshot=True |
| 1381 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1382 | ok | step | sources=['pyobjc_ax', 'macapptree'] agreement=0.7 |
| 1383 | ok | observation |  |
| 1384 | ok | observation |  |
| 1385 | ok | forward_task |  |
| 1386 | ok | world_patch | conversation |
| 1387 | ok | fusion_conflicts |  |
| 1388 | ok | goal_status |  |
| 1389 | ok | decision_engine |  |
| 1390 | ok | planner_decision |  |
| 1391 | ok | execution | open Search via pressed Search via AXPress |
| 1392 | ok | step | transition settle |
| 1393 | ok | step | app=WhatsApp screenshot=True |
| 1394 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1395 | ok | step | sources=['pyobjc_ax', 'macapptree'] agreement=0.7 |
| 1396 | ok | observation |  |
| 1397 | ok | step | transition poll |
| 1398 | ok | step | app=WhatsApp screenshot=True |
| 1399 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1400 | ok | step | sources=['pyobjc_ax', 'macapptree'] agreement=0.7 |
| 1401 | ok | observation |  |
| 1402 | ok | step | transition poll |
| 1403 | ok | perception_retry |  |
| 1404 | ok | step | perception retry (fusion_agreement_low) |
| 1405 | ok | perception_retry_mode |  |
| 1406 | ok | step | app=WhatsApp screenshot=True |
| 1407 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1408 | ok | step | sources=['pyobjc_ax', 'macapptree'] agreement=0.7 |
| 1409 | ok | observation |  |
| 1410 | fail | perception_unsettled |  |
| 1411 | ok | post_observation |  |
| 1412 | ok | post_world_patch |  |
| 1413 | fail | transition_eval |  |
| 1414 | ok | transition_attribution |  |
| 1415 | fail | verification |  |
| 1416 | ok | step | app=WhatsApp screenshot=True |
| 1417 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1418 | ok | step | sources=['pyobjc_ax', 'macapptree'] agreement=0.7 |
| 1419 | ok | observation |  |
| 1420 | ok | post_transition_richer_reobserve |  |
| 1421 | fail | forward_predicate_rollback |  |
| 1422 | ok | step | app=WhatsApp screenshot=True |
| 1423 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1424 | ok | step | sources=['pyobjc_ax', 'macapptree'] agreement=0.7 |
| 1425 | ok | observation |  |
| 1426 | ok | observation |  |
| 1427 | ok | forward_task |  |
| 1428 | ok | world_patch | conversation |
| 1429 | ok | fusion_conflicts |  |
| 1430 | ok | goal_status |  |
| 1431 | ok | decision_engine |  |
| 1432 | ok | planner_decision |  |
| 1433 | ok | execution | pressed Escape |
| 1434 | ok | step | transition settle |
| 1435 | ok | step | app=WhatsApp screenshot=True |
| 1436 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1437 | ok | step | sources=['pyobjc_ax', 'macapptree'] agreement=0.7 |
| 1438 | ok | observation |  |
| 1439 | ok | step | transition poll |
| 1440 | ok | step | app=WhatsApp screenshot=True |
| 1441 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1442 | ok | step | sources=['pyobjc_ax', 'macapptree'] agreement=0.7 |
| 1443 | ok | observation |  |
| 1444 | ok | step | transition poll |
| 1445 | ok | perception_retry |  |
| 1446 | ok | step | perception retry (fusion_agreement_low) |
| 1447 | ok | perception_retry_mode |  |
| 1448 | ok | step | app=WhatsApp screenshot=True |
| 1449 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1450 | ok | step | sources=['pyobjc_ax', 'macapptree'] agreement=0.7 |
| 1451 | ok | observation |  |
| 1452 | fail | perception_unsettled |  |
| 1453 | ok | post_observation |  |
| 1454 | ok | post_world_patch |  |
| 1455 | fail | transition_eval |  |
| 1456 | ok | transition_attribution |  |
| 1457 | fail | verification |  |
| 1458 | ok | step | app=WhatsApp screenshot=True |
| 1459 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1460 | ok | step | sources=['pyobjc_ax', 'macapptree'] agreement=0.7 |
| 1461 | ok | observation |  |
| 1462 | ok | post_transition_richer_reobserve |  |
| 1463 | fail | forward_predicate_rollback |  |
| 1464 | ok | step | app=WhatsApp screenshot=True |
| 1465 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1466 | ok | step | sources=['pyobjc_ax', 'macapptree'] agreement=0.7 |
| 1467 | ok | observation |  |
| 1468 | ok | observation |  |
| 1469 | ok | forward_task |  |
| 1470 | ok | world_patch | conversation |
| 1471 | ok | fusion_conflicts |  |
| 1472 | ok | goal_status |  |
| 1473 | ok | decision_engine |  |
| 1474 | ok | planner_decision |  |
| 1475 | ok | step | re-perceive current world (actuation/world uncertainty) |
| 1476 | ok | step | app=WhatsApp screenshot=True |
| 1477 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1478 | ok | step | sources=['pyobjc_ax', 'macapptree'] agreement=0.7 |
| 1479 | ok | observation |  |
| 1480 | ok | observation |  |
| 1481 | ok | forward_task |  |
| 1482 | ok | world_patch | conversation |
| 1483 | ok | fusion_conflicts |  |
| 1484 | ok | goal_status |  |
| 1485 | ok | decision_engine |  |
| 1486 | ok | planner_decision |  |
| 1487 | fail | execution | no editable field confirmed for 'Kulvinder'; attempts=['open=pressed Search via AXPress', 'editable_field=missing', 'ope |
| 1488 | fail | transition_attribution |  |
| 1489 | ok | step | app=WhatsApp screenshot=True |
| 1490 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1491 | ok | step | sources=['pyobjc_ax', 'macapptree'] agreement=0.7 |
| 1492 | ok | observation |  |
| 1493 | ok | observation |  |
| 1494 | ok | forward_task |  |
| 1495 | ok | world_patch | conversation |
| 1496 | ok | fusion_conflicts |  |
| 1497 | ok | goal_status |  |
| 1498 | ok | decision_engine |  |
| 1499 | ok | planner_decision |  |
| 1500 | ok | execution | pressed Escape |
| 1501 | ok | step | transition settle |
| 1502 | ok | step | app=WhatsApp screenshot=True |
| 1503 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1504 | ok | step | sources=['pyobjc_ax', 'macapptree'] agreement=0.7 |
| 1505 | ok | observation |  |
| 1506 | ok | step | transition poll |
| 1507 | ok | step | app=WhatsApp screenshot=True |
| 1508 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1509 | ok | step | sources=['pyobjc_ax', 'macapptree'] agreement=0.7 |
| 1510 | ok | observation |  |
| 1511 | ok | step | transition poll |
| 1512 | ok | perception_retry |  |
| 1513 | ok | step | perception retry (fusion_agreement_low) |
| 1514 | ok | perception_retry_mode |  |
| 1515 | ok | step | app=WhatsApp screenshot=True |
| 1516 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1517 | ok | step | sources=['pyobjc_ax', 'macapptree'] agreement=0.7 |
| 1518 | ok | observation |  |
| 1519 | fail | perception_unsettled |  |
| 1520 | ok | post_observation |  |
| 1521 | ok | post_world_patch |  |
| 1522 | fail | transition_eval |  |
| 1523 | ok | transition_attribution |  |
| 1524 | fail | verification |  |
| 1525 | ok | step | app=WhatsApp screenshot=True |
| 1526 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1527 | ok | step | sources=['pyobjc_ax', 'macapptree'] agreement=0.7 |
| 1528 | ok | observation |  |
| 1529 | ok | post_transition_richer_reobserve |  |
| 1530 | fail | forward_predicate_rollback |  |
| 1531 | ok | step | app=WhatsApp screenshot=True |
| 1532 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1533 | ok | step | sources=['pyobjc_ax', 'macapptree'] agreement=0.7 |
| 1534 | ok | observation |  |
| 1535 | ok | observation |  |
| 1536 | ok | forward_task |  |
| 1537 | ok | world_patch | conversation |
| 1538 | ok | fusion_conflicts |  |
| 1539 | ok | goal_status |  |
| 1540 | ok | decision_engine |  |
| 1541 | ok | planner_decision |  |
| 1542 | ok | execution | open Search via pressed Search via AXPress |
| 1543 | ok | step | transition settle |
| 1544 | ok | step | app=WhatsApp screenshot=True |
| 1545 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1546 | ok | step | sources=['pyobjc_ax', 'macapptree'] agreement=0.7 |
| 1547 | ok | observation |  |
| 1548 | ok | step | transition poll |
| 1549 | ok | perception_retry |  |
| 1550 | ok | step | perception retry (fusion_agreement_low) |
| 1551 | ok | perception_retry_mode |  |
| 1552 | ok | step | app=WhatsApp screenshot=True |
| 1553 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1554 | ok | step | sources=['pyobjc_ax', 'macapptree'] agreement=0.7 |
| 1555 | ok | observation |  |
| 1556 | fail | perception_unsettled |  |
| 1557 | ok | post_observation |  |
| 1558 | ok | post_world_patch |  |
| 1559 | fail | transition_eval |  |
| 1560 | ok | transition_attribution |  |
| 1561 | fail | verification |  |
| 1562 | ok | step | app=WhatsApp screenshot=True |
| 1563 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1564 | ok | step | sources=['pyobjc_ax', 'macapptree'] agreement=0.7 |
| 1565 | ok | observation |  |
| 1566 | ok | post_transition_richer_reobserve |  |
| 1567 | fail | forward_predicate_rollback |  |
| 1568 | ok | step | app=WhatsApp screenshot=True |
| 1569 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1570 | ok | step | sources=['pyobjc_ax', 'macapptree'] agreement=0.7 |
| 1571 | ok | observation |  |
| 1572 | ok | observation |  |
| 1573 | ok | forward_task |  |
| 1574 | ok | world_patch | conversation |
| 1575 | ok | fusion_conflicts |  |
| 1576 | ok | goal_status |  |
| 1577 | ok | decision_engine |  |
| 1578 | ok | planner_decision |  |
| 1579 | ok | step | re-perceive current world (actuation/world uncertainty) |
| 1580 | ok | step | app=WhatsApp screenshot=True |
| 1581 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1582 | ok | step | fallback=pyobjc_ax |
| 1583 | ok | step | nodes=1 elapsed=0.00s |
| 1584 | ok | observation |  |
| 1585 | ok | observation |  |
| 1586 | ok | forward_task |  |
| 1587 | ok | world_patch | conversation |
| 1588 | ok | goal_status |  |
| 1589 | ok | decision_engine |  |
| 1590 | ok | planner_decision |  |
| 1591 | fail | execution | no editable field confirmed for 'Kulvinder'; attempts=['open=Cmd+F search shortcut (no textfield confirmed)', 'editable_ |
| 1592 | fail | transition_attribution |  |
| 1593 | ok | step | app=WhatsApp screenshot=True |
| 1594 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1595 | ok | step | fallback=pyobjc_ax |
| 1596 | ok | step | nodes=1 elapsed=0.00s |
| 1597 | ok | observation |  |
| 1598 | ok | observation |  |
| 1599 | ok | forward_task |  |
| 1600 | ok | world_patch | conversation |
| 1601 | ok | goal_status |  |
| 1602 | ok | decision_engine |  |
| 1603 | ok | planner_decision |  |
| 1604 | ok | execution | open Search via Cmd+F search shortcut (no textfield confirmed) |
| 1605 | ok | step | transition settle |
| 1606 | ok | step | app=WhatsApp screenshot=True |
| 1607 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1608 | ok | step | fallback=pyobjc_ax |
| 1609 | ok | step | nodes=1 elapsed=0.00s |
| 1610 | ok | observation |  |
| 1611 | ok | step | transition poll |
| 1612 | ok | step | app=WhatsApp screenshot=True |
| 1613 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1614 | ok | step | fallback=pyobjc_ax |
| 1615 | ok | step | nodes=1 elapsed=0.00s |
| 1616 | ok | observation |  |
| 1617 | ok | step | transition poll |
| 1618 | ok | step | app=WhatsApp screenshot=True |
| 1619 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1620 | ok | step | fallback=pyobjc_ax |
| 1621 | ok | step | nodes=1 elapsed=0.00s |
| 1622 | ok | observation |  |
| 1623 | ok | step | transition poll |
| 1624 | ok | perception_retry |  |
| 1625 | ok | step | perception retry (fusion_agreement_low) |
| 1626 | ok | perception_retry_mode |  |
| 1627 | ok | step | app=WhatsApp screenshot=True |
| 1628 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1629 | ok | step | fallback=pyobjc_ax |
| 1630 | ok | step | nodes=1 elapsed=0.00s |
| 1631 | ok | observation |  |
| 1632 | fail | perception_unsettled |  |
| 1633 | ok | post_observation |  |
| 1634 | ok | post_world_patch |  |
| 1635 | fail | transition_eval |  |
| 1636 | ok | transition_attribution |  |
| 1637 | fail | verification |  |
| 1638 | ok | step | app=WhatsApp screenshot=True |
| 1639 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1640 | ok | step | fallback=pyobjc_ax |
| 1641 | ok | step | nodes=1 elapsed=0.00s |
| 1642 | ok | observation |  |
| 1643 | ok | post_transition_richer_reobserve |  |
| 1644 | fail | forward_predicate_rollback |  |
| 1645 | ok | step | app=WhatsApp screenshot=True |
| 1646 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1647 | ok | step | fallback=pyobjc_ax |
| 1648 | ok | step | nodes=1 elapsed=0.00s |
| 1649 | ok | observation |  |
| 1650 | ok | observation |  |
| 1651 | ok | forward_task |  |
| 1652 | ok | world_patch | conversation |
| 1653 | ok | goal_status |  |
| 1654 | ok | decision_engine |  |
| 1655 | ok | planner_decision |  |
| 1656 | ok | step | re-perceive current world (actuation/world uncertainty) |
| 1657 | ok | step | app=WhatsApp screenshot=True |
| 1658 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1659 | ok | step | fallback=pyobjc_ax |
| 1660 | ok | step | nodes=1 elapsed=0.00s |
| 1661 | ok | observation |  |
| 1662 | ok | observation |  |
| 1663 | ok | forward_task |  |
| 1664 | ok | world_patch | conversation |
| 1665 | ok | goal_status |  |
| 1666 | ok | decision_engine |  |
| 1667 | ok | planner_decision |  |
| 1668 | ok | step | re-perceive current world (actuation/world uncertainty) |
| 1669 | ok | step | app=WhatsApp screenshot=True |
| 1670 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1671 | ok | step | fallback=pyobjc_ax |
| 1672 | ok | step | nodes=1 elapsed=0.00s |
| 1673 | ok | observation |  |
| 1674 | ok | observation |  |
| 1675 | ok | forward_task |  |
| 1676 | ok | world_patch | conversation |
| 1677 | ok | goal_status |  |
| 1678 | ok | decision_engine |  |
| 1679 | ok | planner_decision |  |
| 1680 | fail | execution | no editable field confirmed for 'Kulvinder'; attempts=['open=Cmd+F search shortcut (no textfield confirmed)', 'editable_ |
| 1681 | fail | transition_attribution |  |
| 1682 | ok | step | app=WhatsApp screenshot=True |
| 1683 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1684 | ok | step | fallback=pyobjc_ax |
| 1685 | ok | step | nodes=1 elapsed=0.00s |
| 1686 | ok | observation |  |
| 1687 | ok | observation |  |
| 1688 | ok | forward_task |  |
| 1689 | ok | world_patch | conversation |
| 1690 | ok | goal_status |  |
| 1691 | ok | decision_engine |  |
| 1692 | ok | planner_decision |  |
| 1693 | ok | execution | open Search via Cmd+F search shortcut (no textfield confirmed) |
| 1694 | ok | step | transition settle |
| 1695 | ok | step | app=WhatsApp screenshot=True |
| 1696 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1697 | ok | step | fallback=pyobjc_ax |
| 1698 | ok | step | nodes=1 elapsed=0.00s |
| 1699 | ok | observation |  |
| 1700 | ok | step | transition poll |
| 1701 | ok | step | app=WhatsApp screenshot=True |
| 1702 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1703 | ok | step | fallback=pyobjc_ax |
| 1704 | ok | step | nodes=1 elapsed=0.00s |
| 1705 | ok | observation |  |
| 1706 | ok | step | transition poll |
| 1707 | ok | step | app=WhatsApp screenshot=True |
| 1708 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1709 | ok | step | fallback=pyobjc_ax |
| 1710 | ok | step | nodes=1 elapsed=0.00s |
| 1711 | ok | observation |  |
| 1712 | ok | step | transition poll |
| 1713 | ok | step | app=WhatsApp screenshot=True |
| 1714 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1715 | ok | step | fallback=pyobjc_ax |
| 1716 | ok | step | nodes=1 elapsed=0.00s |
| 1717 | ok | observation |  |
| 1718 | ok | step | transition poll |
| 1719 | ok | perception_retry |  |
| 1720 | ok | step | perception retry (fusion_agreement_low) |
| 1721 | ok | perception_retry_mode |  |
| 1722 | ok | step | app=WhatsApp screenshot=True |
| 1723 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1724 | ok | step | fallback=pyobjc_ax |
| 1725 | ok | step | nodes=1 elapsed=0.00s |
| 1726 | ok | observation |  |
| 1727 | fail | perception_unsettled |  |
| 1728 | ok | post_observation |  |
| 1729 | ok | post_world_patch |  |
| 1730 | fail | transition_eval |  |
| 1731 | ok | transition_attribution |  |
| 1732 | fail | verification |  |
| 1733 | ok | step | app=WhatsApp screenshot=True |
| 1734 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1735 | ok | step | fallback=pyobjc_ax |
| 1736 | ok | step | nodes=1 elapsed=0.00s |
| 1737 | ok | observation |  |
| 1738 | ok | post_transition_richer_reobserve |  |
| 1739 | fail | forward_predicate_rollback |  |
| 1740 | ok | step | app=WhatsApp screenshot=True |
| 1741 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1742 | ok | step | fallback=pyobjc_ax |
| 1743 | ok | step | nodes=1 elapsed=0.00s |
| 1744 | ok | observation |  |
| 1745 | ok | observation |  |
| 1746 | ok | forward_task |  |
| 1747 | ok | world_patch | conversation |
| 1748 | ok | goal_status |  |
| 1749 | ok | decision_engine |  |
| 1750 | ok | planner_decision |  |
| 1751 | ok | step | re-perceive current world (actuation/world uncertainty) |
| 1752 | ok | step | app=WhatsApp screenshot=True |
| 1753 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1754 | ok | step | fallback=pyobjc_ax |
| 1755 | ok | step | nodes=1 elapsed=0.00s |
| 1756 | ok | observation |  |
| 1757 | ok | observation |  |
| 1758 | ok | forward_task |  |
| 1759 | ok | world_patch | conversation |
| 1760 | ok | goal_status |  |
| 1761 | ok | decision_engine |  |
| 1762 | ok | planner_decision |  |
| 1763 | ok | step | re-perceive current world (actuation/world uncertainty) |
| 1764 | ok | step | app=WhatsApp screenshot=True |
| 1765 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1766 | ok | step | fallback=pyobjc_ax |
| 1767 | ok | step | nodes=1 elapsed=0.00s |
| 1768 | ok | observation |  |
| 1769 | ok | observation |  |
| 1770 | ok | forward_task |  |
| 1771 | ok | world_patch | conversation |
| 1772 | ok | goal_status |  |
| 1773 | ok | decision_engine |  |
| 1774 | ok | planner_decision |  |
| 1775 | fail | execution | no editable field confirmed for 'Kulvinder'; attempts=['open=Cmd+F search shortcut (no textfield confirmed)', 'editable_ |
| 1776 | fail | transition_attribution |  |
| 1777 | ok | step | app=WhatsApp screenshot=True |
| 1778 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1779 | ok | step | fallback=pyobjc_ax |
| 1780 | ok | step | nodes=1 elapsed=0.00s |
| 1781 | ok | observation |  |
| 1782 | ok | observation |  |
| 1783 | ok | forward_task |  |
| 1784 | ok | world_patch | conversation |
| 1785 | ok | goal_status |  |
| 1786 | ok | decision_engine |  |
| 1787 | ok | planner_decision |  |
| 1788 | ok | execution | open Search via Cmd+F search shortcut (no textfield confirmed) |
| 1789 | ok | step | transition settle |
| 1790 | ok | step | app=WhatsApp screenshot=True |
| 1791 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1792 | ok | step | fallback=pyobjc_ax |
| 1793 | ok | step | nodes=1 elapsed=0.00s |
| 1794 | ok | observation |  |
| 1795 | ok | step | transition poll |
| 1796 | ok | step | app=WhatsApp screenshot=True |
| 1797 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1798 | ok | step | fallback=pyobjc_ax |
| 1799 | ok | step | nodes=1 elapsed=0.00s |
| 1800 | ok | observation |  |
| 1801 | ok | step | transition poll |
| 1802 | ok | step | app=WhatsApp screenshot=True |
| 1803 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1804 | ok | step | fallback=pyobjc_ax |
| 1805 | ok | step | nodes=1 elapsed=0.00s |
| 1806 | ok | observation |  |
| 1807 | ok | step | transition poll |
| 1808 | ok | step | app=WhatsApp screenshot=True |
| 1809 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1810 | ok | step | fallback=pyobjc_ax |
| 1811 | ok | step | nodes=1 elapsed=0.00s |
| 1812 | ok | observation |  |
| 1813 | ok | step | transition poll |
| 1814 | ok | perception_retry |  |
| 1815 | ok | step | perception retry (fusion_agreement_low) |
| 1816 | ok | perception_retry_mode |  |
| 1817 | ok | step | app=WhatsApp screenshot=True |
| 1818 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1819 | ok | step | fallback=pyobjc_ax |
| 1820 | ok | step | nodes=1 elapsed=0.00s |
| 1821 | ok | observation |  |
| 1822 | fail | perception_unsettled |  |
| 1823 | ok | post_observation |  |
| 1824 | ok | post_world_patch |  |
| 1825 | fail | transition_eval |  |
| 1826 | ok | transition_attribution |  |
| 1827 | fail | verification |  |
| 1828 | ok | step | app=WhatsApp screenshot=True |
| 1829 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1830 | ok | step | fallback=pyobjc_ax |
| 1831 | ok | step | nodes=1 elapsed=0.00s |
| 1832 | ok | observation |  |
| 1833 | ok | post_transition_richer_reobserve |  |
| 1834 | fail | forward_predicate_rollback |  |
| 1835 | ok | step | app=WhatsApp screenshot=True |
| 1836 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1837 | ok | step | fallback=pyobjc_ax |
| 1838 | ok | step | nodes=1 elapsed=0.00s |
| 1839 | ok | observation |  |
| 1840 | ok | observation |  |
| 1841 | ok | forward_task |  |
| 1842 | ok | world_patch | conversation |
| 1843 | ok | goal_status |  |
| 1844 | ok | decision_engine |  |
| 1845 | ok | planner_decision |  |
| 1846 | ok | step | re-perceive current world (actuation/world uncertainty) |
| 1847 | ok | step | app=WhatsApp screenshot=True |
| 1848 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1849 | ok | step | fallback=pyobjc_ax |
| 1850 | ok | step | nodes=1 elapsed=0.00s |
| 1851 | ok | observation |  |
| 1852 | ok | observation |  |
| 1853 | ok | forward_task |  |
| 1854 | ok | world_patch | conversation |
| 1855 | ok | goal_status |  |
| 1856 | ok | decision_engine |  |
| 1857 | ok | planner_decision |  |
| 1858 | ok | step | re-perceive current world (actuation/world uncertainty) |
| 1859 | ok | step | app=WhatsApp screenshot=True |
| 1860 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1861 | ok | step | fallback=pyobjc_ax |
| 1862 | ok | step | nodes=1 elapsed=0.00s |
| 1863 | ok | observation |  |
| 1864 | ok | observation |  |
| 1865 | ok | forward_task |  |
| 1866 | ok | world_patch | conversation |
| 1867 | ok | goal_status |  |
| 1868 | ok | decision_engine |  |
| 1869 | ok | planner_decision |  |
| 1870 | fail | execution | no editable field confirmed for 'Kulvinder'; attempts=['open=Cmd+F search shortcut (no textfield confirmed)', 'editable_ |
| 1871 | fail | transition_attribution |  |
| 1872 | ok | step | app=WhatsApp screenshot=True |
| 1873 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1874 | ok | step | fallback=pyobjc_ax |
| 1875 | ok | step | nodes=1 elapsed=0.00s |
| 1876 | ok | observation |  |
| 1877 | ok | observation |  |
| 1878 | ok | forward_task |  |
| 1879 | ok | world_patch | conversation |
| 1880 | ok | goal_status |  |
| 1881 | ok | decision_engine |  |
| 1882 | ok | planner_decision |  |
| 1883 | ok | execution | open Search via Cmd+F search shortcut (no textfield confirmed) |
| 1884 | ok | step | transition settle |
| 1885 | ok | step | app=WhatsApp screenshot=True |
| 1886 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1887 | ok | step | fallback=pyobjc_ax |
| 1888 | ok | step | nodes=1 elapsed=0.00s |
| 1889 | ok | observation |  |
| 1890 | ok | step | transition poll |
| 1891 | ok | step | app=WhatsApp screenshot=True |
| 1892 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1893 | ok | step | fallback=pyobjc_ax |
| 1894 | ok | step | nodes=1 elapsed=0.00s |
| 1895 | ok | observation |  |
| 1896 | ok | step | transition poll |
| 1897 | ok | step | app=WhatsApp screenshot=True |
| 1898 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1899 | ok | step | fallback=pyobjc_ax |
| 1900 | ok | step | nodes=1 elapsed=0.00s |
| 1901 | ok | observation |  |
| 1902 | ok | step | transition poll |
| 1903 | ok | step | app=WhatsApp screenshot=True |
| 1904 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1905 | ok | step | fallback=pyobjc_ax |
| 1906 | ok | step | nodes=1 elapsed=0.00s |
| 1907 | ok | observation |  |
| 1908 | ok | step | transition poll |
| 1909 | ok | perception_retry |  |
| 1910 | ok | step | perception retry (fusion_agreement_low) |
| 1911 | ok | perception_retry_mode |  |
| 1912 | ok | step | app=WhatsApp screenshot=True |
| 1913 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1914 | ok | step | fallback=pyobjc_ax |
| 1915 | ok | step | nodes=1 elapsed=0.00s |
| 1916 | ok | observation |  |
| 1917 | fail | perception_unsettled |  |
| 1918 | ok | post_observation |  |
| 1919 | ok | post_world_patch |  |
| 1920 | fail | transition_eval |  |
| 1921 | ok | transition_attribution |  |
| 1922 | fail | verification |  |
| 1923 | ok | step | app=WhatsApp screenshot=True |
| 1924 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1925 | ok | step | fallback=pyobjc_ax |
| 1926 | ok | step | nodes=1 elapsed=0.00s |
| 1927 | ok | observation |  |
| 1928 | ok | post_transition_richer_reobserve |  |
| 1929 | fail | forward_predicate_rollback |  |
| 1930 | ok | step | app=WhatsApp screenshot=True |
| 1931 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1932 | ok | step | fallback=pyobjc_ax |
| 1933 | ok | step | nodes=1 elapsed=0.00s |
| 1934 | ok | observation |  |
| 1935 | ok | observation |  |
| 1936 | ok | forward_task |  |
| 1937 | ok | world_patch | conversation |
| 1938 | ok | goal_status |  |
| 1939 | ok | decision_engine |  |
| 1940 | ok | planner_decision |  |
| 1941 | ok | step | re-perceive current world (actuation/world uncertainty) |
| 1942 | ok | step | app=WhatsApp screenshot=True |
| 1943 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1944 | ok | step | fallback=pyobjc_ax |
| 1945 | ok | step | nodes=1 elapsed=0.00s |
| 1946 | ok | observation |  |
| 1947 | ok | observation |  |
| 1948 | ok | forward_task |  |
| 1949 | ok | world_patch | conversation |
| 1950 | ok | goal_status |  |
| 1951 | ok | decision_engine |  |
| 1952 | ok | planner_decision |  |
| 1953 | ok | step | re-perceive current world (actuation/world uncertainty) |
| 1954 | ok | step | app=WhatsApp screenshot=True |
| 1955 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1956 | ok | step | fallback=pyobjc_ax |
| 1957 | ok | step | nodes=1 elapsed=0.00s |
| 1958 | ok | observation |  |
| 1959 | ok | observation |  |
| 1960 | ok | forward_task |  |
| 1961 | ok | world_patch | conversation |
| 1962 | ok | goal_status |  |
| 1963 | ok | decision_engine |  |
| 1964 | ok | planner_decision |  |
| 1965 | fail | execution | no editable field confirmed for 'Kulvinder'; attempts=['open=Cmd+F search shortcut (no textfield confirmed)', 'editable_ |
| 1966 | fail | transition_attribution |  |
| 1967 | ok | step | app=WhatsApp screenshot=True |
| 1968 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1969 | ok | step | fallback=pyobjc_ax |
| 1970 | ok | step | nodes=1 elapsed=0.00s |
| 1971 | ok | observation |  |
| 1972 | ok | observation |  |
| 1973 | ok | forward_task |  |
| 1974 | ok | world_patch | conversation |
| 1975 | ok | goal_status |  |
| 1976 | ok | decision_engine |  |
| 1977 | ok | planner_decision |  |
| 1978 | ok | execution | open Search via Cmd+F search shortcut (no textfield confirmed) |
| 1979 | ok | step | transition settle |
| 1980 | ok | step | app=WhatsApp screenshot=True |
| 1981 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1982 | ok | step | fallback=pyobjc_ax |
| 1983 | ok | step | nodes=1 elapsed=0.00s |
| 1984 | ok | observation |  |
| 1985 | ok | step | transition poll |
| 1986 | ok | step | app=WhatsApp screenshot=True |
| 1987 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1988 | ok | step | fallback=pyobjc_ax |
| 1989 | ok | step | nodes=1 elapsed=0.00s |
| 1990 | ok | observation |  |
| 1991 | ok | step | transition poll |
| 1992 | ok | step | app=WhatsApp screenshot=True |
| 1993 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 1994 | ok | step | fallback=pyobjc_ax |
| 1995 | ok | step | nodes=1 elapsed=0.00s |
| 1996 | ok | observation |  |
| 1997 | ok | step | transition poll |
| 1998 | ok | perception_retry |  |
| 1999 | ok | step | perception retry (fusion_agreement_low) |
| 2000 | ok | perception_retry_mode |  |
| 2001 | ok | step | app=WhatsApp screenshot=True |
| 2002 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 2003 | ok | step | fallback=pyobjc_ax |
| 2004 | ok | step | nodes=1 elapsed=0.00s |
| 2005 | ok | observation |  |
| 2006 | fail | perception_unsettled |  |
| 2007 | ok | post_observation |  |
| 2008 | ok | post_world_patch |  |
| 2009 | fail | transition_eval |  |
| 2010 | ok | transition_attribution |  |
| 2011 | fail | verification |  |
| 2012 | ok | step | app=WhatsApp screenshot=True |
| 2013 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 2014 | ok | step | fallback=pyobjc_ax |
| 2015 | ok | step | nodes=1 elapsed=0.00s |
| 2016 | ok | observation |  |
| 2017 | ok | post_transition_richer_reobserve |  |
| 2018 | fail | forward_predicate_rollback |  |
| 2019 | ok | step | app=WhatsApp screenshot=True |
| 2020 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 2021 | ok | step | fallback=pyobjc_ax |
| 2022 | ok | step | nodes=1 elapsed=0.00s |
| 2023 | ok | observation |  |
| 2024 | ok | observation |  |
| 2025 | ok | forward_task |  |
| 2026 | ok | world_patch | conversation |
| 2027 | ok | goal_status |  |
| 2028 | ok | decision_engine |  |
| 2029 | ok | planner_decision |  |
| 2030 | ok | step | re-perceive current world (actuation/world uncertainty) |
| 2031 | ok | step | app=WhatsApp screenshot=True |
| 2032 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 2033 | ok | step | fallback=pyobjc_ax |
| 2034 | ok | step | nodes=1 elapsed=0.00s |
| 2035 | ok | observation |  |
| 2036 | ok | observation |  |
| 2037 | ok | forward_task |  |
| 2038 | ok | world_patch | conversation |
| 2039 | ok | goal_status |  |
| 2040 | ok | decision_engine |  |
| 2041 | ok | planner_decision |  |
| 2042 | ok | step | re-perceive current world (actuation/world uncertainty) |
| 2043 | ok | step | app=WhatsApp screenshot=True |
| 2044 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 2045 | ok | step | fallback=pyobjc_ax |
| 2046 | ok | step | nodes=1 elapsed=0.00s |
| 2047 | ok | observation |  |
| 2048 | ok | observation |  |
| 2049 | ok | forward_task |  |
| 2050 | ok | world_patch | conversation |
| 2051 | ok | goal_status |  |
| 2052 | ok | decision_engine |  |
| 2053 | ok | planner_decision |  |
| 2054 | fail | execution | no editable field confirmed for 'Kulvinder'; attempts=['open=Cmd+F search shortcut (no textfield confirmed)', 'editable_ |
| 2055 | fail | transition_attribution |  |
| 2056 | ok | step | app=WhatsApp screenshot=True |
| 2057 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 2058 | ok | step | fallback=pyobjc_ax |
| 2059 | ok | step | nodes=1 elapsed=0.00s |
| 2060 | ok | observation |  |
| 2061 | ok | observation |  |
| 2062 | ok | forward_task |  |
| 2063 | ok | world_patch | conversation |
| 2064 | ok | goal_status |  |
| 2065 | ok | decision_engine |  |
| 2066 | ok | planner_decision |  |
| 2067 | ok | execution | open Search via Cmd+F search shortcut (no textfield confirmed) |
| 2068 | ok | step | transition settle |
| 2069 | ok | step | app=WhatsApp screenshot=True |
| 2070 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 2071 | ok | step | fallback=pyobjc_ax |
| 2072 | ok | step | nodes=1 elapsed=0.00s |
| 2073 | ok | observation |  |
| 2074 | ok | step | transition poll |
| 2075 | ok | step | app=WhatsApp screenshot=True |
| 2076 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 2077 | ok | step | fallback=pyobjc_ax |
| 2078 | ok | step | nodes=1 elapsed=0.00s |
| 2079 | ok | observation |  |
| 2080 | ok | step | transition poll |
| 2081 | ok | step | app=WhatsApp screenshot=True |
| 2082 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 2083 | ok | step | fallback=pyobjc_ax |
| 2084 | ok | step | nodes=1 elapsed=0.00s |
| 2085 | ok | observation |  |
| 2086 | ok | step | transition poll |
| 2087 | ok | step | app=WhatsApp screenshot=True |
| 2088 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 2089 | ok | step | fallback=pyobjc_ax |
| 2090 | ok | step | nodes=1 elapsed=0.00s |
| 2091 | ok | observation |  |
| 2092 | ok | step | transition poll |
| 2093 | ok | perception_retry |  |
| 2094 | ok | step | perception retry (fusion_agreement_low) |
| 2095 | ok | perception_retry_mode |  |
| 2096 | ok | step | app=WhatsApp screenshot=True |
| 2097 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 2098 | ok | step | fallback=pyobjc_ax |
| 2099 | ok | step | nodes=1 elapsed=0.00s |
| 2100 | ok | observation |  |
| 2101 | fail | perception_unsettled |  |
| 2102 | ok | post_observation |  |
| 2103 | ok | post_world_patch |  |
| 2104 | fail | transition_eval |  |
| 2105 | ok | transition_attribution |  |
| 2106 | fail | verification |  |
| 2107 | ok | step | app=WhatsApp screenshot=True |
| 2108 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 2109 | ok | step | fallback=pyobjc_ax |
| 2110 | ok | step | nodes=1 elapsed=0.00s |
| 2111 | ok | observation |  |
| 2112 | ok | post_transition_richer_reobserve |  |
| 2113 | fail | forward_predicate_rollback |  |
| 2114 | ok | step | app=WhatsApp screenshot=True |
| 2115 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 2116 | ok | step | fallback=pyobjc_ax |
| 2117 | ok | step | nodes=1 elapsed=0.00s |
| 2118 | ok | observation |  |
| 2119 | ok | observation |  |
| 2120 | ok | forward_task |  |
| 2121 | ok | world_patch | conversation |
| 2122 | ok | goal_status |  |
| 2123 | ok | decision_engine |  |
| 2124 | ok | planner_decision |  |
| 2125 | ok | step | re-perceive current world (actuation/world uncertainty) |
| 2126 | ok | step | app=WhatsApp screenshot=True |
| 2127 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 2128 | ok | step | fallback=pyobjc_ax |
| 2129 | ok | step | nodes=1 elapsed=0.00s |
| 2130 | ok | observation |  |
| 2131 | ok | observation |  |
| 2132 | ok | forward_task |  |
| 2133 | ok | world_patch | conversation |
| 2134 | ok | goal_status |  |
| 2135 | ok | decision_engine |  |
| 2136 | ok | planner_decision |  |
| 2137 | ok | step | re-perceive current world (actuation/world uncertainty) |
| 2138 | ok | step | app=WhatsApp screenshot=True |
| 2139 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 2140 | ok | step | fallback=pyobjc_ax |
| 2141 | ok | step | nodes=1 elapsed=0.00s |
| 2142 | ok | observation |  |
| 2143 | ok | observation |  |
| 2144 | ok | forward_task |  |
| 2145 | ok | world_patch | conversation |
| 2146 | ok | goal_status |  |
| 2147 | ok | decision_engine |  |
| 2148 | ok | planner_decision |  |
| 2149 | fail | execution | no editable field confirmed for 'Kulvinder'; attempts=['open=Cmd+F search shortcut (no textfield confirmed)', 'editable_ |
| 2150 | fail | transition_attribution |  |
| 2151 | ok | step | app=WhatsApp screenshot=True |
| 2152 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 2153 | ok | step | fallback=pyobjc_ax |
| 2154 | ok | step | nodes=1 elapsed=0.00s |
| 2155 | ok | observation |  |
| 2156 | ok | observation |  |
| 2157 | ok | forward_task |  |
| 2158 | ok | world_patch | conversation |
| 2159 | ok | goal_status |  |
| 2160 | ok | decision_engine |  |
| 2161 | ok | planner_decision |  |
| 2162 | ok | execution | open Search via Cmd+F search shortcut (no textfield confirmed) |
| 2163 | ok | step | transition settle |
| 2164 | ok | step | app=WhatsApp screenshot=True |
| 2165 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 2166 | ok | step | fallback=pyobjc_ax |
| 2167 | ok | step | nodes=1 elapsed=0.00s |
| 2168 | ok | observation |  |
| 2169 | ok | step | transition poll |
| 2170 | ok | step | app=WhatsApp screenshot=True |
| 2171 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 2172 | ok | step | fallback=pyobjc_ax |
| 2173 | ok | step | nodes=1 elapsed=0.00s |
| 2174 | ok | observation |  |
| 2175 | ok | step | transition poll |
| 2176 | ok | step | app=WhatsApp screenshot=True |
| 2177 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 2178 | ok | step | fallback=pyobjc_ax |
| 2179 | ok | step | nodes=1 elapsed=0.00s |
| 2180 | ok | observation |  |
| 2181 | ok | step | transition poll |
| 2182 | ok | step | app=WhatsApp screenshot=True |
| 2183 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 2184 | ok | step | fallback=pyobjc_ax |
| 2185 | ok | step | nodes=1 elapsed=0.00s |
| 2186 | ok | observation |  |
| 2187 | ok | step | transition poll |
| 2188 | ok | perception_retry |  |
| 2189 | ok | step | perception retry (fusion_agreement_low) |
| 2190 | ok | perception_retry_mode |  |
| 2191 | ok | step | app=WhatsApp screenshot=True |
| 2192 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 2193 | ok | step | fallback=pyobjc_ax |
| 2194 | ok | step | nodes=1 elapsed=0.00s |
| 2195 | ok | observation |  |
| 2196 | fail | perception_unsettled |  |
| 2197 | ok | post_observation |  |
| 2198 | ok | post_world_patch |  |
| 2199 | fail | transition_eval |  |
| 2200 | ok | transition_attribution |  |
| 2201 | fail | verification |  |
| 2202 | ok | step | app=WhatsApp screenshot=True |
| 2203 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 2204 | ok | step | fallback=pyobjc_ax |
| 2205 | ok | step | nodes=1 elapsed=0.00s |
| 2206 | ok | observation |  |
| 2207 | ok | post_transition_richer_reobserve |  |
| 2208 | fail | forward_predicate_rollback |  |
| 2209 | ok | step | app=WhatsApp screenshot=True |
| 2210 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 2211 | ok | step | fallback=pyobjc_ax |
| 2212 | ok | step | nodes=1 elapsed=0.00s |
| 2213 | ok | observation |  |
| 2214 | ok | observation |  |
| 2215 | ok | forward_task |  |
| 2216 | ok | world_patch | conversation |
| 2217 | ok | goal_status |  |
| 2218 | ok | decision_engine |  |
| 2219 | ok | planner_decision |  |
| 2220 | ok | step | re-perceive current world (actuation/world uncertainty) |
| 2221 | ok | step | app=WhatsApp screenshot=True |
| 2222 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 2223 | ok | step | fallback=pyobjc_ax |
| 2224 | ok | step | nodes=1 elapsed=0.00s |
| 2225 | ok | observation |  |
| 2226 | ok | observation |  |
| 2227 | ok | forward_task |  |
| 2228 | ok | world_patch | conversation |
| 2229 | ok | goal_status |  |
| 2230 | ok | decision_engine |  |
| 2231 | ok | planner_decision |  |
| 2232 | ok | step | re-perceive current world (actuation/world uncertainty) |
| 2233 | ok | step | app=WhatsApp screenshot=True |
| 2234 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 2235 | ok | step | fallback=pyobjc_ax |
| 2236 | ok | step | nodes=1 elapsed=0.00s |
| 2237 | ok | observation |  |
| 2238 | ok | observation |  |
| 2239 | ok | forward_task |  |
| 2240 | ok | world_patch | conversation |
| 2241 | ok | goal_status |  |
| 2242 | ok | decision_engine |  |
| 2243 | ok | planner_decision |  |
| 2244 | fail | execution | no editable field confirmed for 'Kulvinder'; attempts=['open=Cmd+F search shortcut (no textfield confirmed)', 'editable_ |
| 2245 | fail | transition_attribution |  |
| 2246 | ok | step | app=WhatsApp screenshot=True |
| 2247 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 2248 | ok | step | fallback=pyobjc_ax |
| 2249 | ok | step | nodes=1 elapsed=0.00s |
| 2250 | ok | observation |  |
| 2251 | ok | observation |  |
| 2252 | ok | forward_task |  |
| 2253 | ok | world_patch | conversation |
| 2254 | ok | goal_status |  |
| 2255 | ok | decision_engine |  |
| 2256 | ok | planner_decision |  |
| 2257 | ok | execution | open Search via Cmd+F search shortcut (no textfield confirmed) |
| 2258 | ok | step | transition settle |
| 2259 | ok | step | app=WhatsApp screenshot=True |
| 2260 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 2261 | ok | step | fallback=pyobjc_ax |
| 2262 | ok | step | nodes=1 elapsed=0.00s |
| 2263 | ok | observation |  |
| 2264 | ok | step | transition poll |
| 2265 | ok | step | app=WhatsApp screenshot=True |
| 2266 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 2267 | ok | step | fallback=pyobjc_ax |
| 2268 | ok | step | nodes=1 elapsed=0.00s |
| 2269 | ok | observation |  |
| 2270 | ok | step | transition poll |
| 2271 | ok | step | app=WhatsApp screenshot=True |
| 2272 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 2273 | ok | step | fallback=pyobjc_ax |
| 2274 | ok | step | nodes=1 elapsed=0.00s |
| 2275 | ok | observation |  |
| 2276 | ok | step | transition poll |
| 2277 | ok | step | app=WhatsApp screenshot=True |
| 2278 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 2279 | ok | step | fallback=pyobjc_ax |
| 2280 | ok | step | nodes=1 elapsed=0.00s |
| 2281 | ok | observation |  |
| 2282 | ok | step | transition poll |
| 2283 | ok | perception_retry |  |
| 2284 | ok | step | perception retry (fusion_agreement_low) |
| 2285 | ok | perception_retry_mode |  |
| 2286 | ok | step | app=WhatsApp screenshot=True |
| 2287 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 2288 | ok | step | fallback=pyobjc_ax |
| 2289 | ok | step | nodes=1 elapsed=0.00s |
| 2290 | ok | observation |  |
| 2291 | fail | perception_unsettled |  |
| 2292 | ok | post_observation |  |
| 2293 | ok | post_world_patch |  |
| 2294 | fail | transition_eval |  |
| 2295 | ok | transition_attribution |  |
| 2296 | fail | verification |  |
| 2297 | ok | step | app=WhatsApp screenshot=True |
| 2298 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 2299 | ok | step | fallback=pyobjc_ax |
| 2300 | ok | step | nodes=1 elapsed=0.00s |
| 2301 | ok | observation |  |
| 2302 | ok | post_transition_richer_reobserve |  |
| 2303 | fail | forward_predicate_rollback |  |
| 2304 | ok | step | app=WhatsApp screenshot=True |
| 2305 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 2306 | ok | step | fallback=pyobjc_ax |
| 2307 | ok | step | nodes=1 elapsed=0.00s |
| 2308 | ok | observation |  |
| 2309 | ok | observation |  |
| 2310 | ok | forward_task |  |
| 2311 | ok | world_patch | conversation |
| 2312 | ok | goal_status |  |
| 2313 | ok | decision_engine |  |
| 2314 | ok | planner_decision |  |
| 2315 | ok | step | re-perceive current world (actuation/world uncertainty) |
| 2316 | ok | step | app=WhatsApp screenshot=True |
| 2317 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 2318 | ok | step | fallback=pyobjc_ax |
| 2319 | ok | step | nodes=1 elapsed=0.00s |
| 2320 | ok | observation |  |
| 2321 | ok | observation |  |
| 2322 | ok | forward_task |  |
| 2323 | ok | world_patch | conversation |
| 2324 | ok | goal_status |  |
| 2325 | ok | decision_engine |  |
| 2326 | ok | planner_decision |  |
| 2327 | ok | step | re-perceive current world (actuation/world uncertainty) |
| 2328 | ok | step | app=WhatsApp screenshot=True |
| 2329 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 2330 | ok | step | fallback=pyobjc_ax |
| 2331 | ok | step | nodes=1 elapsed=0.00s |
| 2332 | ok | observation |  |
| 2333 | ok | observation |  |
| 2334 | ok | forward_task |  |
| 2335 | ok | world_patch | conversation |
| 2336 | ok | goal_status |  |
| 2337 | ok | decision_engine |  |
| 2338 | ok | planner_decision |  |
| 2339 | fail | execution | no editable field confirmed for 'Kulvinder'; attempts=['open=Cmd+F search shortcut (no textfield confirmed)', 'editable_ |
| 2340 | fail | transition_attribution |  |
| 2341 | ok | step | app=WhatsApp screenshot=True |
| 2342 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 2343 | ok | step | fallback=pyobjc_ax |
| 2344 | ok | step | nodes=1 elapsed=0.00s |
| 2345 | ok | observation |  |
| 2346 | ok | observation |  |
| 2347 | ok | forward_task |  |
| 2348 | ok | world_patch | conversation |
| 2349 | ok | goal_status |  |
| 2350 | ok | decision_engine |  |
| 2351 | ok | planner_decision |  |
| 2352 | ok | execution | open Search via Cmd+F search shortcut (no textfield confirmed) |
| 2353 | ok | step | transition settle |
| 2354 | ok | step | app=WhatsApp screenshot=True |
| 2355 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 2356 | ok | step | fallback=pyobjc_ax |
| 2357 | ok | step | nodes=1 elapsed=0.00s |
| 2358 | ok | observation |  |
| 2359 | ok | step | transition poll |
| 2360 | ok | step | app=WhatsApp screenshot=True |
| 2361 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 2362 | ok | step | fallback=pyobjc_ax |
| 2363 | ok | step | nodes=1 elapsed=0.00s |
| 2364 | ok | observation |  |
| 2365 | ok | step | transition poll |
| 2366 | ok | step | app=WhatsApp screenshot=True |
| 2367 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 2368 | ok | step | fallback=pyobjc_ax |
| 2369 | ok | step | nodes=1 elapsed=0.00s |
| 2370 | ok | observation |  |
| 2371 | ok | step | transition poll |
| 2372 | ok | step | app=WhatsApp screenshot=True |
| 2373 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 2374 | ok | step | fallback=pyobjc_ax |
| 2375 | ok | step | nodes=1 elapsed=0.00s |
| 2376 | ok | observation |  |
| 2377 | ok | step | transition poll |
| 2378 | ok | perception_retry |  |
| 2379 | ok | step | perception retry (fusion_agreement_low) |
| 2380 | ok | perception_retry_mode |  |
| 2381 | ok | step | app=WhatsApp screenshot=True |
| 2382 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 2383 | ok | step | fallback=pyobjc_ax |
| 2384 | ok | step | nodes=1 elapsed=0.00s |
| 2385 | ok | observation |  |
| 2386 | fail | perception_unsettled |  |
| 2387 | ok | post_observation |  |
| 2388 | ok | post_world_patch |  |
| 2389 | fail | transition_eval |  |
| 2390 | ok | transition_attribution |  |
| 2391 | fail | verification |  |
| 2392 | ok | step | app=WhatsApp screenshot=True |
| 2393 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 2394 | ok | step | fallback=pyobjc_ax |
| 2395 | ok | step | nodes=1 elapsed=0.00s |
| 2396 | ok | observation |  |
| 2397 | ok | post_transition_richer_reobserve |  |
| 2398 | fail | forward_predicate_rollback |  |
| 2399 | ok | step | app=WhatsApp screenshot=True |
| 2400 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 2401 | ok | step | fallback=pyobjc_ax |
| 2402 | ok | step | nodes=1 elapsed=0.00s |
| 2403 | ok | observation |  |
| 2404 | ok | observation |  |
| 2405 | ok | forward_task |  |
| 2406 | ok | world_patch | conversation |
| 2407 | ok | goal_status |  |
| 2408 | ok | decision_engine |  |
| 2409 | ok | planner_decision |  |
| 2410 | ok | step | re-perceive current world (actuation/world uncertainty) |
| 2411 | ok | step | app=WhatsApp screenshot=True |
| 2412 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 2413 | ok | step | fallback=pyobjc_ax |
| 2414 | ok | step | nodes=1 elapsed=0.00s |
| 2415 | ok | observation |  |
| 2416 | ok | observation |  |
| 2417 | ok | forward_task |  |
| 2418 | ok | world_patch | conversation |
| 2419 | ok | goal_status |  |
| 2420 | ok | decision_engine |  |
| 2421 | ok | planner_decision |  |
| 2422 | ok | step | re-perceive current world (actuation/world uncertainty) |
| 2423 | ok | step | app=WhatsApp screenshot=True |
| 2424 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 2425 | ok | step | fallback=pyobjc_ax |
| 2426 | ok | step | nodes=1 elapsed=0.00s |
| 2427 | ok | observation |  |
| 2428 | ok | observation |  |
| 2429 | ok | forward_task |  |
| 2430 | ok | world_patch | conversation |
| 2431 | ok | goal_status |  |
| 2432 | ok | decision_engine |  |
| 2433 | ok | planner_decision |  |
| 2434 | fail | execution | no editable field confirmed for 'Kulvinder'; attempts=['open=Cmd+F search shortcut (no textfield confirmed)', 'editable_ |
| 2435 | fail | transition_attribution |  |
| 2436 | ok | step | app=WhatsApp screenshot=True |
| 2437 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 2438 | ok | step | fallback=pyobjc_ax |
| 2439 | ok | step | nodes=1 elapsed=0.00s |
| 2440 | ok | observation |  |
| 2441 | ok | observation |  |
| 2442 | ok | forward_task |  |
| 2443 | ok | world_patch | conversation |
| 2444 | ok | goal_status |  |
| 2445 | ok | decision_engine |  |
| 2446 | ok | planner_decision |  |
| 2447 | ok | execution | open Search via Cmd+F search shortcut (no textfield confirmed) |
| 2448 | ok | step | transition settle |
| 2449 | ok | step | app=WhatsApp screenshot=True |
| 2450 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 2451 | ok | step | fallback=pyobjc_ax |
| 2452 | ok | step | nodes=1 elapsed=0.00s |
| 2453 | ok | observation |  |
| 2454 | ok | step | transition poll |
| 2455 | ok | step | app=WhatsApp screenshot=True |
| 2456 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 2457 | ok | step | fallback=pyobjc_ax |
| 2458 | ok | step | nodes=1 elapsed=0.00s |
| 2459 | ok | observation |  |
| 2460 | ok | step | transition poll |
| 2461 | ok | step | app=WhatsApp screenshot=True |
| 2462 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 2463 | ok | step | fallback=pyobjc_ax |
| 2464 | ok | step | nodes=1 elapsed=0.00s |
| 2465 | ok | observation |  |
| 2466 | ok | step | transition poll |
| 2467 | ok | perception_retry |  |
| 2468 | ok | step | perception retry (fusion_agreement_low) |
| 2469 | ok | perception_retry_mode |  |
| 2470 | ok | step | app=WhatsApp screenshot=True |
| 2471 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 2472 | ok | step | fallback=pyobjc_ax |
| 2473 | ok | step | nodes=1 elapsed=0.00s |
| 2474 | ok | observation |  |
| 2475 | fail | perception_unsettled |  |
| 2476 | ok | post_observation |  |
| 2477 | ok | post_world_patch |  |
| 2478 | fail | transition_eval |  |
| 2479 | ok | transition_attribution |  |
| 2480 | fail | verification |  |
| 2481 | ok | step | app=WhatsApp screenshot=True |
| 2482 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 2483 | ok | step | fallback=pyobjc_ax |
| 2484 | ok | step | nodes=1 elapsed=0.00s |
| 2485 | ok | observation |  |
| 2486 | ok | post_transition_richer_reobserve |  |
| 2487 | fail | forward_predicate_rollback |  |
| 2488 | ok | step | app=WhatsApp screenshot=True |
| 2489 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 2490 | ok | step | fallback=pyobjc_ax |
| 2491 | ok | step | nodes=1 elapsed=0.00s |
| 2492 | ok | observation |  |
| 2493 | ok | observation |  |
| 2494 | ok | forward_task |  |
| 2495 | ok | world_patch | conversation |
| 2496 | ok | goal_status |  |
| 2497 | ok | decision_engine |  |
| 2498 | ok | planner_decision |  |
| 2499 | ok | step | re-perceive current world (actuation/world uncertainty) |
| 2500 | ok | step | app=WhatsApp screenshot=True |
| 2501 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 2502 | ok | step | fallback=pyobjc_ax |
| 2503 | ok | step | nodes=1 elapsed=0.00s |
| 2504 | ok | observation |  |
| 2505 | ok | observation |  |
| 2506 | ok | forward_task |  |
| 2507 | ok | world_patch | conversation |
| 2508 | ok | goal_status |  |
| 2509 | ok | decision_engine |  |
| 2510 | ok | planner_decision |  |
| 2511 | ok | step | re-perceive current world (actuation/world uncertainty) |
| 2512 | ok | step | app=WhatsApp screenshot=True |
| 2513 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 2514 | ok | step | fallback=pyobjc_ax |
| 2515 | ok | step | nodes=1 elapsed=0.00s |
| 2516 | ok | observation |  |
| 2517 | ok | observation |  |
| 2518 | ok | forward_task |  |
| 2519 | ok | world_patch | conversation |
| 2520 | ok | goal_status |  |
| 2521 | ok | decision_engine |  |
| 2522 | ok | planner_decision |  |
| 2523 | fail | execution | no editable field confirmed for 'Kulvinder'; attempts=['open=Cmd+F search shortcut (no textfield confirmed)', 'editable_ |
| 2524 | fail | transition_attribution |  |
| 2525 | ok | step | app=WhatsApp screenshot=True |
| 2526 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 2527 | ok | step | fallback=pyobjc_ax |
| 2528 | ok | step | nodes=1 elapsed=0.00s |
| 2529 | ok | observation |  |
| 2530 | ok | observation |  |
| 2531 | ok | forward_task |  |
| 2532 | ok | world_patch | conversation |
| 2533 | ok | goal_status |  |
| 2534 | ok | decision_engine |  |
| 2535 | ok | planner_decision |  |
| 2536 | ok | execution | open Search via Cmd+F search shortcut (no textfield confirmed) |
| 2537 | ok | step | transition settle |
| 2538 | ok | step | app=WhatsApp screenshot=True |
| 2539 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 2540 | ok | step | fallback=pyobjc_ax |
| 2541 | ok | step | nodes=1 elapsed=0.00s |
| 2542 | ok | observation |  |
| 2543 | ok | step | transition poll |
| 2544 | ok | step | app=WhatsApp screenshot=True |
| 2545 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 2546 | ok | step | fallback=pyobjc_ax |
| 2547 | ok | step | nodes=1 elapsed=0.00s |
| 2548 | ok | observation |  |
| 2549 | ok | step | transition poll |
| 2550 | ok | step | app=WhatsApp screenshot=True |
| 2551 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 2552 | ok | step | fallback=pyobjc_ax |
| 2553 | ok | step | nodes=1 elapsed=0.00s |
| 2554 | ok | observation |  |
| 2555 | ok | step | transition poll |
| 2556 | ok | step | app=WhatsApp screenshot=True |
| 2557 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 2558 | ok | step | fallback=pyobjc_ax |
| 2559 | ok | step | nodes=1 elapsed=0.00s |
| 2560 | ok | observation |  |
| 2561 | ok | step | transition poll |
| 2562 | ok | perception_retry |  |
| 2563 | ok | step | perception retry (fusion_agreement_low) |
| 2564 | ok | perception_retry_mode |  |
| 2565 | ok | step | app=WhatsApp screenshot=True |
| 2566 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 2567 | ok | step | fallback=pyobjc_ax |
| 2568 | ok | step | nodes=1 elapsed=0.00s |
| 2569 | ok | observation |  |
| 2570 | fail | perception_unsettled |  |
| 2571 | ok | post_observation |  |
| 2572 | ok | post_world_patch |  |
| 2573 | fail | transition_eval |  |
| 2574 | ok | transition_attribution |  |
| 2575 | fail | verification |  |
| 2576 | ok | step | app=WhatsApp screenshot=True |
| 2577 | ok | step | prefer_source=pyobjc_ax secondary=True |
| 2578 | ok | step | fallback=pyobjc_ax |
| 2579 | ok | step | nodes=1 elapsed=0.00s |
| 2580 | ok | observation |  |
| 2581 | ok | post_transition_richer_reobserve |  |
| 2582 | fail | forward_predicate_rollback |  |
| 2583 | ok | world_summary |  |
| 2584 | fail | check | fail |
| 2585 | fail | run_end | closed_loop ok=False reason='Maximum step count reached' iterations=99 |

## Failures

- seq=5 `check`: {"ts": 1785214544.5664482, "seq": 5, "run_id": "wa-forward-live-1785214544", "kind": "check", "status": "fail", "name": "ghost_cli_installed", "expected": true, "actual": false, "message": "fail", "st
- seq=33 `execution`: {"ts": 1785214638.043558, "seq": 33, "run_id": "wa-forward-live-1785214544", "kind": "execution", "status": "fail", "ok": false, "backend": "ax", "message": "no editable field confirmed for 'Kulvinder
- seq=34 `transition_attribution`: {"ts": 1785214638.044721, "seq": 34, "run_id": "wa-forward-live-1785214544", "kind": "transition_attribution", "status": "fail", "action_family": "type_query", "outcome": "no_effect", "effect_kind": "
- seq=65 `perception_unsettled`: {"ts": 1785214687.6257322, "seq": 65, "run_id": "wa-forward-live-1785214544", "kind": "perception_unsettled", "status": "fail", "settled": false, "failure_modes": ["fusion_agreement_low"], "retry_stra
- seq=68 `transition_eval`: {"ts": 1785214687.650814, "seq": 68, "run_id": "wa-forward-live-1785214544", "kind": "transition_eval", "status": "fail", "attempt": {"before_world_id": "w0", "after_world_id": "w0", "action_family": 
- seq=70 `verification`: {"ts": 1785214687.650995, "seq": 70, "run_id": "wa-forward-live-1785214544", "kind": "verification", "status": "fail", "passed": false, "reason": "no_effect", "expected_predicate": "TransitionEvaluato
- seq=76 `forward_predicate_rollback`: {"ts": 1785214688.22606, "seq": 76, "run_id": "wa-forward-live-1785214544", "kind": "forward_predicate_rollback", "status": "fail", "expected": "SearchInputFocused", "outcome": "no_effect", "forward_t
- seq=112 `execution`: {"ts": 1785214717.33923, "seq": 112, "run_id": "wa-forward-live-1785214544", "kind": "execution", "status": "fail", "ok": false, "backend": "ax", "message": "no editable field confirmed for 'Kulvinder
- seq=113 `transition_attribution`: {"ts": 1785214717.340107, "seq": 113, "run_id": "wa-forward-live-1785214544", "kind": "transition_attribution", "status": "fail", "action_family": "type_query", "outcome": "no_effect", "effect_kind": 
- seq=143 `perception_unsettled`: {"ts": 1785214764.7033238, "seq": 143, "run_id": "wa-forward-live-1785214544", "kind": "perception_unsettled", "status": "fail", "settled": false, "failure_modes": ["fusion_agreement_low"], "retry_str
- seq=146 `transition_eval`: {"ts": 1785214764.7287302, "seq": 146, "run_id": "wa-forward-live-1785214544", "kind": "transition_eval", "status": "fail", "attempt": {"before_world_id": "w0", "after_world_id": "w0", "action_family"
- seq=148 `verification`: {"ts": 1785214764.72908, "seq": 148, "run_id": "wa-forward-live-1785214544", "kind": "verification", "status": "fail", "passed": false, "reason": "no_effect", "expected_predicate": "TransitionEvaluato
- seq=154 `forward_predicate_rollback`: {"ts": 1785214765.2921972, "seq": 154, "run_id": "wa-forward-live-1785214544", "kind": "forward_predicate_rollback", "status": "fail", "expected": "SearchInputFocused", "outcome": "no_effect", "forwar
- seq=187 `execution`: {"ts": 1785214807.892041, "seq": 187, "run_id": "wa-forward-live-1785214544", "kind": "execution", "status": "fail", "ok": false, "backend": "ax", "message": "no editable field confirmed for 'Kulvinde
- seq=188 `transition_attribution`: {"ts": 1785214807.893467, "seq": 188, "run_id": "wa-forward-live-1785214544", "kind": "transition_attribution", "status": "fail", "action_family": "type_query", "outcome": "no_effect", "effect_kind": 
- seq=219 `perception_unsettled`: {"ts": 1785214906.281695, "seq": 219, "run_id": "wa-forward-live-1785214544", "kind": "perception_unsettled", "status": "fail", "settled": false, "failure_modes": ["fusion_agreement_low"], "retry_stra
- seq=222 `transition_eval`: {"ts": 1785214906.3077528, "seq": 222, "run_id": "wa-forward-live-1785214544", "kind": "transition_eval", "status": "fail", "attempt": {"before_world_id": "w0", "after_world_id": "w0", "action_family"
- seq=224 `verification`: {"ts": 1785214906.3080142, "seq": 224, "run_id": "wa-forward-live-1785214544", "kind": "verification", "status": "fail", "passed": false, "reason": "no_effect", "expected_predicate": "TransitionEvalua
- seq=230 `forward_predicate_rollback`: {"ts": 1785214906.921622, "seq": 230, "run_id": "wa-forward-live-1785214544", "kind": "forward_predicate_rollback", "status": "fail", "expected": "NoUnexpectedDialog", "outcome": "no_effect", "forward
- seq=261 `perception_unsettled`: {"ts": 1785214962.768448, "seq": 261, "run_id": "wa-forward-live-1785214544", "kind": "perception_unsettled", "status": "fail", "settled": false, "failure_modes": ["fusion_agreement_low"], "retry_stra
- seq=264 `transition_eval`: {"ts": 1785214962.7942998, "seq": 264, "run_id": "wa-forward-live-1785214544", "kind": "transition_eval", "status": "fail", "attempt": {"before_world_id": "w0", "after_world_id": "w0", "action_family"
- seq=266 `verification`: {"ts": 1785214962.794473, "seq": 266, "run_id": "wa-forward-live-1785214544", "kind": "verification", "status": "fail", "passed": false, "reason": "no_effect", "expected_predicate": "TransitionEvaluat
- seq=272 `forward_predicate_rollback`: {"ts": 1785214963.374156, "seq": 272, "run_id": "wa-forward-live-1785214544", "kind": "forward_predicate_rollback", "status": "fail", "expected": "SearchInputFocused", "outcome": "no_effect", "forward
- seq=315 `perception_unsettled`: {"ts": 1785215074.676945, "seq": 315, "run_id": "wa-forward-live-1785214544", "kind": "perception_unsettled", "status": "fail", "settled": false, "failure_modes": ["fusion_agreement_low"], "retry_stra
- seq=318 `transition_eval`: {"ts": 1785215074.702622, "seq": 318, "run_id": "wa-forward-live-1785214544", "kind": "transition_eval", "status": "fail", "attempt": {"before_world_id": "w0", "after_world_id": "w0", "action_family":
- seq=320 `verification`: {"ts": 1785215074.702781, "seq": 320, "run_id": "wa-forward-live-1785214544", "kind": "verification", "status": "fail", "passed": false, "reason": "no_effect", "expected_predicate": "TransitionEvaluat
- seq=326 `forward_predicate_rollback`: {"ts": 1785215075.280225, "seq": 326, "run_id": "wa-forward-live-1785214544", "kind": "forward_predicate_rollback", "status": "fail", "expected": "NoUnexpectedDialog", "outcome": "no_effect", "forward
- seq=338 `execution`: {"ts": 1785215110.366644, "seq": 338, "run_id": "wa-forward-live-1785214544", "kind": "execution", "status": "fail", "ok": false, "backend": "ax", "message": "no editable field confirmed for 'Kulvinde
- seq=339 `transition_attribution`: {"ts": 1785215110.369813, "seq": 339, "run_id": "wa-forward-live-1785214544", "kind": "transition_attribution", "status": "fail", "action_family": "type_query", "outcome": "no_effect", "effect_kind": 
- seq=370 `perception_unsettled`: {"ts": 1785215153.929759, "seq": 370, "run_id": "wa-forward-live-1785214544", "kind": "perception_unsettled", "status": "fail", "settled": false, "failure_modes": ["fusion_agreement_low"], "retry_stra
- seq=373 `transition_eval`: {"ts": 1785215153.9554791, "seq": 373, "run_id": "wa-forward-live-1785214544", "kind": "transition_eval", "status": "fail", "attempt": {"before_world_id": "w0", "after_world_id": "w0", "action_family"
- seq=375 `verification`: {"ts": 1785215153.95565, "seq": 375, "run_id": "wa-forward-live-1785214544", "kind": "verification", "status": "fail", "passed": false, "reason": "no_effect", "expected_predicate": "TransitionEvaluato
- seq=381 `forward_predicate_rollback`: {"ts": 1785215154.533398, "seq": 381, "run_id": "wa-forward-live-1785214544", "kind": "forward_predicate_rollback", "status": "fail", "expected": "SearchInputFocused", "outcome": "no_effect", "forward
- seq=412 `perception_unsettled`: {"ts": 1785215182.64131, "seq": 412, "run_id": "wa-forward-live-1785214544", "kind": "perception_unsettled", "status": "fail", "settled": false, "failure_modes": ["fusion_agreement_low"], "retry_strat
- seq=415 `transition_eval`: {"ts": 1785215182.66693, "seq": 415, "run_id": "wa-forward-live-1785214544", "kind": "transition_eval", "status": "fail", "attempt": {"before_world_id": "w0", "after_world_id": "w0", "action_family": 
- seq=417 `verification`: {"ts": 1785215182.66711, "seq": 417, "run_id": "wa-forward-live-1785214544", "kind": "verification", "status": "fail", "passed": false, "reason": "no_effect", "expected_predicate": "TransitionEvaluato
- seq=423 `forward_predicate_rollback`: {"ts": 1785215183.288286, "seq": 423, "run_id": "wa-forward-live-1785214544", "kind": "forward_predicate_rollback", "status": "fail", "expected": "NoUnexpectedDialog", "outcome": "no_effect", "forward
- seq=447 `execution`: {"ts": 1785215200.660342, "seq": 447, "run_id": "wa-forward-live-1785214544", "kind": "execution", "status": "fail", "ok": false, "backend": "ax", "message": "no editable field confirmed for 'Kulvinde
- seq=448 `transition_attribution`: {"ts": 1785215200.661186, "seq": 448, "run_id": "wa-forward-live-1785214544", "kind": "transition_attribution", "status": "fail", "action_family": "type_query", "outcome": "no_effect", "effect_kind": 
- seq=479 `perception_unsettled`: {"ts": 1785215237.1779509, "seq": 479, "run_id": "wa-forward-live-1785214544", "kind": "perception_unsettled", "status": "fail", "settled": false, "failure_modes": ["fusion_agreement_low"], "retry_str
- seq=482 `transition_eval`: {"ts": 1785215237.203564, "seq": 482, "run_id": "wa-forward-live-1785214544", "kind": "transition_eval", "status": "fail", "attempt": {"before_world_id": "w0", "after_world_id": "w0", "action_family":
- seq=484 `verification`: {"ts": 1785215237.203729, "seq": 484, "run_id": "wa-forward-live-1785214544", "kind": "verification", "status": "fail", "passed": false, "reason": "no_effect", "expected_predicate": "TransitionEvaluat
- seq=490 `forward_predicate_rollback`: {"ts": 1785215237.7842822, "seq": 490, "run_id": "wa-forward-live-1785214544", "kind": "forward_predicate_rollback", "status": "fail", "expected": "NoUnexpectedDialog", "outcome": "no_effect", "forwar
- seq=521 `perception_unsettled`: {"ts": 1785215264.158308, "seq": 521, "run_id": "wa-forward-live-1785214544", "kind": "perception_unsettled", "status": "fail", "settled": false, "failure_modes": ["fusion_agreement_low"], "retry_stra
- seq=524 `transition_eval`: {"ts": 1785215264.183899, "seq": 524, "run_id": "wa-forward-live-1785214544", "kind": "transition_eval", "status": "fail", "attempt": {"before_world_id": "w0", "after_world_id": "w0", "action_family":
- seq=526 `verification`: {"ts": 1785215264.184075, "seq": 526, "run_id": "wa-forward-live-1785214544", "kind": "verification", "status": "fail", "passed": false, "reason": "no_effect", "expected_predicate": "TransitionEvaluat
- seq=532 `forward_predicate_rollback`: {"ts": 1785215264.810115, "seq": 532, "run_id": "wa-forward-live-1785214544", "kind": "forward_predicate_rollback", "status": "fail", "expected": "SearchInputFocused", "outcome": "no_effect", "forward
- seq=575 `perception_unsettled`: {"ts": 1785215274.6524749, "seq": 575, "run_id": "wa-forward-live-1785214544", "kind": "perception_unsettled", "status": "fail", "settled": false, "failure_modes": ["fusion_agreement_low"], "retry_str
- seq=578 `transition_eval`: {"ts": 1785215274.679992, "seq": 578, "run_id": "wa-forward-live-1785214544", "kind": "transition_eval", "status": "fail", "attempt": {"before_world_id": "w0", "after_world_id": "w0", "action_family":
- seq=580 `verification`: {"ts": 1785215274.680275, "seq": 580, "run_id": "wa-forward-live-1785214544", "kind": "verification", "status": "fail", "passed": false, "reason": "no_effect", "expected_predicate": "TransitionEvaluat
- seq=586 `forward_predicate_rollback`: {"ts": 1785215275.3027751, "seq": 586, "run_id": "wa-forward-live-1785214544", "kind": "forward_predicate_rollback", "status": "fail", "expected": "NoUnexpectedDialog", "outcome": "no_effect", "forwar
- seq=598 `execution`: {"ts": 1785215301.0580978, "seq": 598, "run_id": "wa-forward-live-1785214544", "kind": "execution", "status": "fail", "ok": false, "backend": "ax", "message": "no editable field confirmed for 'Kulvind
- seq=599 `transition_attribution`: {"ts": 1785215301.058691, "seq": 599, "run_id": "wa-forward-live-1785214544", "kind": "transition_attribution", "status": "fail", "action_family": "type_query", "outcome": "no_effect", "effect_kind": 
- seq=630 `perception_unsettled`: {"ts": 1785215312.6426141, "seq": 630, "run_id": "wa-forward-live-1785214544", "kind": "perception_unsettled", "status": "fail", "settled": false, "failure_modes": ["fusion_agreement_low"], "retry_str
- seq=633 `transition_eval`: {"ts": 1785215312.668344, "seq": 633, "run_id": "wa-forward-live-1785214544", "kind": "transition_eval", "status": "fail", "attempt": {"before_world_id": "w0", "after_world_id": "w0", "action_family":
- seq=635 `verification`: {"ts": 1785215312.668515, "seq": 635, "run_id": "wa-forward-live-1785214544", "kind": "verification", "status": "fail", "passed": false, "reason": "no_effect", "expected_predicate": "TransitionEvaluat
- seq=641 `forward_predicate_rollback`: {"ts": 1785215313.2938979, "seq": 641, "run_id": "wa-forward-live-1785214544", "kind": "forward_predicate_rollback", "status": "fail", "expected": "SearchInputFocused", "outcome": "no_effect", "forwar
- seq=672 `perception_unsettled`: {"ts": 1785215320.4056299, "seq": 672, "run_id": "wa-forward-live-1785214544", "kind": "perception_unsettled", "status": "fail", "settled": false, "failure_modes": ["fusion_agreement_low"], "retry_str
- seq=675 `transition_eval`: {"ts": 1785215320.431726, "seq": 675, "run_id": "wa-forward-live-1785214544", "kind": "transition_eval", "status": "fail", "attempt": {"before_world_id": "w0", "after_world_id": "w0", "action_family":
- seq=677 `verification`: {"ts": 1785215320.431902, "seq": 677, "run_id": "wa-forward-live-1785214544", "kind": "verification", "status": "fail", "passed": false, "reason": "no_effect", "expected_predicate": "TransitionEvaluat
- seq=683 `forward_predicate_rollback`: {"ts": 1785215321.0154839, "seq": 683, "run_id": "wa-forward-live-1785214544", "kind": "forward_predicate_rollback", "status": "fail", "expected": "NoUnexpectedDialog", "outcome": "no_effect", "forwar
- seq=707 `execution`: {"ts": 1785215345.424997, "seq": 707, "run_id": "wa-forward-live-1785214544", "kind": "execution", "status": "fail", "ok": false, "backend": "ax", "message": "no editable field confirmed for 'Kulvinde
- seq=708 `transition_attribution`: {"ts": 1785215345.425589, "seq": 708, "run_id": "wa-forward-live-1785214544", "kind": "transition_attribution", "status": "fail", "action_family": "type_query", "outcome": "no_effect", "effect_kind": 
- seq=739 `perception_unsettled`: {"ts": 1785215360.092384, "seq": 739, "run_id": "wa-forward-live-1785214544", "kind": "perception_unsettled", "status": "fail", "settled": false, "failure_modes": ["fusion_agreement_low"], "retry_stra
- seq=742 `transition_eval`: {"ts": 1785215360.120545, "seq": 742, "run_id": "wa-forward-live-1785214544", "kind": "transition_eval", "status": "fail", "attempt": {"before_world_id": "w0", "after_world_id": "w0", "action_family":
- seq=744 `verification`: {"ts": 1785215360.120832, "seq": 744, "run_id": "wa-forward-live-1785214544", "kind": "verification", "status": "fail", "passed": false, "reason": "no_effect", "expected_predicate": "TransitionEvaluat
- seq=750 `forward_predicate_rollback`: {"ts": 1785215360.705911, "seq": 750, "run_id": "wa-forward-live-1785214544", "kind": "forward_predicate_rollback", "status": "fail", "expected": "NoUnexpectedDialog", "outcome": "no_effect", "forward
- seq=781 `perception_unsettled`: {"ts": 1785215408.95595, "seq": 781, "run_id": "wa-forward-live-1785214544", "kind": "perception_unsettled", "status": "fail", "settled": false, "failure_modes": ["fusion_agreement_low"], "retry_strat
- seq=784 `transition_eval`: {"ts": 1785215408.983315, "seq": 784, "run_id": "wa-forward-live-1785214544", "kind": "transition_eval", "status": "fail", "attempt": {"before_world_id": "w0", "after_world_id": "w0", "action_family":
- seq=786 `verification`: {"ts": 1785215408.98359, "seq": 786, "run_id": "wa-forward-live-1785214544", "kind": "verification", "status": "fail", "passed": false, "reason": "no_effect", "expected_predicate": "TransitionEvaluato
- seq=792 `forward_predicate_rollback`: {"ts": 1785215409.608738, "seq": 792, "run_id": "wa-forward-live-1785214544", "kind": "forward_predicate_rollback", "status": "fail", "expected": "SearchInputFocused", "outcome": "no_effect", "forward
- seq=835 `perception_unsettled`: {"ts": 1785215442.5712588, "seq": 835, "run_id": "wa-forward-live-1785214544", "kind": "perception_unsettled", "status": "fail", "settled": false, "failure_modes": ["fusion_agreement_low"], "retry_str
- seq=838 `transition_eval`: {"ts": 1785215442.596802, "seq": 838, "run_id": "wa-forward-live-1785214544", "kind": "transition_eval", "status": "fail", "attempt": {"before_world_id": "w0", "after_world_id": "w0", "action_family":
- seq=840 `verification`: {"ts": 1785215442.596998, "seq": 840, "run_id": "wa-forward-live-1785214544", "kind": "verification", "status": "fail", "passed": false, "reason": "no_effect", "expected_predicate": "TransitionEvaluat
- seq=846 `forward_predicate_rollback`: {"ts": 1785215443.217597, "seq": 846, "run_id": "wa-forward-live-1785214544", "kind": "forward_predicate_rollback", "status": "fail", "expected": "NoUnexpectedDialog", "outcome": "no_effect", "forward
- seq=858 `execution`: {"ts": 1785215529.7130601, "seq": 858, "run_id": "wa-forward-live-1785214544", "kind": "execution", "status": "fail", "ok": false, "backend": "ax", "message": "no editable field confirmed for 'Kulvind
- seq=859 `transition_attribution`: {"ts": 1785215529.7142131, "seq": 859, "run_id": "wa-forward-live-1785214544", "kind": "transition_attribution", "status": "fail", "action_family": "type_query", "outcome": "no_effect", "effect_kind":
- seq=890 `perception_unsettled`: {"ts": 1785215541.6051588, "seq": 890, "run_id": "wa-forward-live-1785214544", "kind": "perception_unsettled", "status": "fail", "settled": false, "failure_modes": ["fusion_agreement_low"], "retry_str
- seq=893 `transition_eval`: {"ts": 1785215541.630975, "seq": 893, "run_id": "wa-forward-live-1785214544", "kind": "transition_eval", "status": "fail", "attempt": {"before_world_id": "w0", "after_world_id": "w0", "action_family":
- seq=895 `verification`: {"ts": 1785215541.6311512, "seq": 895, "run_id": "wa-forward-live-1785214544", "kind": "verification", "status": "fail", "passed": false, "reason": "no_effect", "expected_predicate": "TransitionEvalua
- seq=901 `forward_predicate_rollback`: {"ts": 1785215542.258949, "seq": 901, "run_id": "wa-forward-live-1785214544", "kind": "forward_predicate_rollback", "status": "fail", "expected": "SearchInputFocused", "outcome": "no_effect", "forward
- seq=932 `perception_unsettled`: {"ts": 1785215555.142344, "seq": 932, "run_id": "wa-forward-live-1785214544", "kind": "perception_unsettled", "status": "fail", "settled": false, "failure_modes": ["fusion_agreement_low"], "retry_stra
- seq=935 `transition_eval`: {"ts": 1785215555.168163, "seq": 935, "run_id": "wa-forward-live-1785214544", "kind": "transition_eval", "status": "fail", "attempt": {"before_world_id": "w0", "after_world_id": "w0", "action_family":
- seq=937 `verification`: {"ts": 1785215555.1685371, "seq": 937, "run_id": "wa-forward-live-1785214544", "kind": "verification", "status": "fail", "passed": false, "reason": "no_effect", "expected_predicate": "TransitionEvalua
- seq=943 `forward_predicate_rollback`: {"ts": 1785215555.789908, "seq": 943, "run_id": "wa-forward-live-1785214544", "kind": "forward_predicate_rollback", "status": "fail", "expected": "NoUnexpectedDialog", "outcome": "no_effect", "forward
- seq=967 `execution`: {"ts": 1785215572.372351, "seq": 967, "run_id": "wa-forward-live-1785214544", "kind": "execution", "status": "fail", "ok": false, "backend": "ax", "message": "no editable field confirmed for 'Kulvinde
- seq=968 `transition_attribution`: {"ts": 1785215572.373438, "seq": 968, "run_id": "wa-forward-live-1785214544", "kind": "transition_attribution", "status": "fail", "action_family": "type_query", "outcome": "no_effect", "effect_kind": 
- seq=999 `perception_unsettled`: {"ts": 1785215586.958712, "seq": 999, "run_id": "wa-forward-live-1785214544", "kind": "perception_unsettled", "status": "fail", "settled": false, "failure_modes": ["fusion_agreement_low"], "retry_stra
- seq=1002 `transition_eval`: {"ts": 1785215586.984422, "seq": 1002, "run_id": "wa-forward-live-1785214544", "kind": "transition_eval", "status": "fail", "attempt": {"before_world_id": "w0", "after_world_id": "w0", "action_family"
- seq=1004 `verification`: {"ts": 1785215586.98459, "seq": 1004, "run_id": "wa-forward-live-1785214544", "kind": "verification", "status": "fail", "passed": false, "reason": "no_effect", "expected_predicate": "TransitionEvaluat
- seq=1010 `forward_predicate_rollback`: {"ts": 1785215587.607572, "seq": 1010, "run_id": "wa-forward-live-1785214544", "kind": "forward_predicate_rollback", "status": "fail", "expected": "NoUnexpectedDialog", "outcome": "no_effect", "forwar
- seq=1041 `perception_unsettled`: {"ts": 1785215604.932883, "seq": 1041, "run_id": "wa-forward-live-1785214544", "kind": "perception_unsettled", "status": "fail", "settled": false, "failure_modes": ["fusion_agreement_low"], "retry_str
- seq=1044 `transition_eval`: {"ts": 1785215604.958664, "seq": 1044, "run_id": "wa-forward-live-1785214544", "kind": "transition_eval", "status": "fail", "attempt": {"before_world_id": "w0", "after_world_id": "w0", "action_family"
- seq=1046 `verification`: {"ts": 1785215604.95883, "seq": 1046, "run_id": "wa-forward-live-1785214544", "kind": "verification", "status": "fail", "passed": false, "reason": "no_effect", "expected_predicate": "TransitionEvaluat
- seq=1052 `forward_predicate_rollback`: {"ts": 1785215605.579206, "seq": 1052, "run_id": "wa-forward-live-1785214544", "kind": "forward_predicate_rollback", "status": "fail", "expected": "SearchInputFocused", "outcome": "no_effect", "forwar
- seq=1095 `perception_unsettled`: {"ts": 1785215619.671084, "seq": 1095, "run_id": "wa-forward-live-1785214544", "kind": "perception_unsettled", "status": "fail", "settled": false, "failure_modes": ["fusion_agreement_low"], "retry_str
- seq=1098 `transition_eval`: {"ts": 1785215619.698142, "seq": 1098, "run_id": "wa-forward-live-1785214544", "kind": "transition_eval", "status": "fail", "attempt": {"before_world_id": "w0", "after_world_id": "w0", "action_family"
- seq=1100 `verification`: {"ts": 1785215619.698445, "seq": 1100, "run_id": "wa-forward-live-1785214544", "kind": "verification", "status": "fail", "passed": false, "reason": "no_effect", "expected_predicate": "TransitionEvalua
- seq=1106 `forward_predicate_rollback`: {"ts": 1785215620.304563, "seq": 1106, "run_id": "wa-forward-live-1785214544", "kind": "forward_predicate_rollback", "status": "fail", "expected": "NoUnexpectedDialog", "outcome": "no_effect", "forwar
- seq=1118 `execution`: {"ts": 1785215638.814807, "seq": 1118, "run_id": "wa-forward-live-1785214544", "kind": "execution", "status": "fail", "ok": false, "backend": "ax", "message": "no editable field confirmed for 'Kulvind
- seq=1119 `transition_attribution`: {"ts": 1785215638.815268, "seq": 1119, "run_id": "wa-forward-live-1785214544", "kind": "transition_attribution", "status": "fail", "action_family": "type_query", "outcome": "no_effect", "effect_kind":
- seq=1150 `perception_unsettled`: {"ts": 1785215654.270335, "seq": 1150, "run_id": "wa-forward-live-1785214544", "kind": "perception_unsettled", "status": "fail", "settled": false, "failure_modes": ["fusion_agreement_low"], "retry_str
- seq=1153 `transition_eval`: {"ts": 1785215654.295935, "seq": 1153, "run_id": "wa-forward-live-1785214544", "kind": "transition_eval", "status": "fail", "attempt": {"before_world_id": "w0", "after_world_id": "w0", "action_family"
- seq=1155 `verification`: {"ts": 1785215654.296095, "seq": 1155, "run_id": "wa-forward-live-1785214544", "kind": "verification", "status": "fail", "passed": false, "reason": "no_effect", "expected_predicate": "TransitionEvalua
- seq=1161 `forward_predicate_rollback`: {"ts": 1785215654.915888, "seq": 1161, "run_id": "wa-forward-live-1785214544", "kind": "forward_predicate_rollback", "status": "fail", "expected": "SearchInputFocused", "outcome": "no_effect", "forwar
- seq=1192 `perception_unsettled`: {"ts": 1785215664.5345259, "seq": 1192, "run_id": "wa-forward-live-1785214544", "kind": "perception_unsettled", "status": "fail", "settled": false, "failure_modes": ["fusion_agreement_low"], "retry_st
- seq=1195 `transition_eval`: {"ts": 1785215664.560087, "seq": 1195, "run_id": "wa-forward-live-1785214544", "kind": "transition_eval", "status": "fail", "attempt": {"before_world_id": "w0", "after_world_id": "w0", "action_family"
- seq=1197 `verification`: {"ts": 1785215664.560287, "seq": 1197, "run_id": "wa-forward-live-1785214544", "kind": "verification", "status": "fail", "passed": false, "reason": "no_effect", "expected_predicate": "TransitionEvalua
- seq=1203 `forward_predicate_rollback`: {"ts": 1785215665.234059, "seq": 1203, "run_id": "wa-forward-live-1785214544", "kind": "forward_predicate_rollback", "status": "fail", "expected": "NoUnexpectedDialog", "outcome": "no_effect", "forwar
- seq=1227 `execution`: {"ts": 1785215685.27324, "seq": 1227, "run_id": "wa-forward-live-1785214544", "kind": "execution", "status": "fail", "ok": false, "backend": "ax", "message": "no editable field confirmed for 'Kulvinde
- seq=1228 `transition_attribution`: {"ts": 1785215685.273654, "seq": 1228, "run_id": "wa-forward-live-1785214544", "kind": "transition_attribution", "status": "fail", "action_family": "type_query", "outcome": "no_effect", "effect_kind":
- seq=1259 `perception_unsettled`: {"ts": 1785215699.895414, "seq": 1259, "run_id": "wa-forward-live-1785214544", "kind": "perception_unsettled", "status": "fail", "settled": false, "failure_modes": ["fusion_agreement_low"], "retry_str
- seq=1262 `transition_eval`: {"ts": 1785215699.9211059, "seq": 1262, "run_id": "wa-forward-live-1785214544", "kind": "transition_eval", "status": "fail", "attempt": {"before_world_id": "w0", "after_world_id": "w0", "action_family
- seq=1264 `verification`: {"ts": 1785215699.921278, "seq": 1264, "run_id": "wa-forward-live-1785214544", "kind": "verification", "status": "fail", "passed": false, "reason": "no_effect", "expected_predicate": "TransitionEvalua
- seq=1270 `forward_predicate_rollback`: {"ts": 1785215700.591135, "seq": 1270, "run_id": "wa-forward-live-1785214544", "kind": "forward_predicate_rollback", "status": "fail", "expected": "NoUnexpectedDialog", "outcome": "no_effect", "forwar
- seq=1301 `perception_unsettled`: {"ts": 1785215719.225846, "seq": 1301, "run_id": "wa-forward-live-1785214544", "kind": "perception_unsettled", "status": "fail", "settled": false, "failure_modes": ["fusion_agreement_low"], "retry_str
- seq=1304 `transition_eval`: {"ts": 1785215719.2517009, "seq": 1304, "run_id": "wa-forward-live-1785214544", "kind": "transition_eval", "status": "fail", "attempt": {"before_world_id": "w0", "after_world_id": "w0", "action_family
- seq=1306 `verification`: {"ts": 1785215719.251884, "seq": 1306, "run_id": "wa-forward-live-1785214544", "kind": "verification", "status": "fail", "passed": false, "reason": "no_effect", "expected_predicate": "TransitionEvalua
- seq=1312 `forward_predicate_rollback`: {"ts": 1785215719.875175, "seq": 1312, "run_id": "wa-forward-live-1785214544", "kind": "forward_predicate_rollback", "status": "fail", "expected": "SearchInputFocused", "outcome": "no_effect", "forwar
- seq=1355 `perception_unsettled`: {"ts": 1785215730.133587, "seq": 1355, "run_id": "wa-forward-live-1785214544", "kind": "perception_unsettled", "status": "fail", "settled": false, "failure_modes": ["fusion_agreement_low"], "retry_str
- seq=1358 `transition_eval`: {"ts": 1785215730.159431, "seq": 1358, "run_id": "wa-forward-live-1785214544", "kind": "transition_eval", "status": "fail", "attempt": {"before_world_id": "w0", "after_world_id": "w0", "action_family"
- seq=1360 `verification`: {"ts": 1785215730.159627, "seq": 1360, "run_id": "wa-forward-live-1785214544", "kind": "verification", "status": "fail", "passed": false, "reason": "no_effect", "expected_predicate": "TransitionEvalua
- seq=1366 `forward_predicate_rollback`: {"ts": 1785215730.8419409, "seq": 1366, "run_id": "wa-forward-live-1785214544", "kind": "forward_predicate_rollback", "status": "fail", "expected": "NoUnexpectedDialog", "outcome": "no_effect", "forwa
- seq=1378 `execution`: {"ts": 1785215745.084542, "seq": 1378, "run_id": "wa-forward-live-1785214544", "kind": "execution", "status": "fail", "ok": false, "backend": "ax", "message": "no editable field confirmed for 'Kulvind
- seq=1379 `transition_attribution`: {"ts": 1785215745.084872, "seq": 1379, "run_id": "wa-forward-live-1785214544", "kind": "transition_attribution", "status": "fail", "action_family": "type_query", "outcome": "no_effect", "effect_kind":
- seq=1410 `perception_unsettled`: {"ts": 1785215761.392755, "seq": 1410, "run_id": "wa-forward-live-1785214544", "kind": "perception_unsettled", "status": "fail", "settled": false, "failure_modes": ["fusion_agreement_low"], "retry_str
- seq=1413 `transition_eval`: {"ts": 1785215761.41873, "seq": 1413, "run_id": "wa-forward-live-1785214544", "kind": "transition_eval", "status": "fail", "attempt": {"before_world_id": "w0", "after_world_id": "w0", "action_family":
- seq=1415 `verification`: {"ts": 1785215761.41906, "seq": 1415, "run_id": "wa-forward-live-1785214544", "kind": "verification", "status": "fail", "passed": false, "reason": "no_effect", "expected_predicate": "TransitionEvaluat
- seq=1421 `forward_predicate_rollback`: {"ts": 1785215762.04082, "seq": 1421, "run_id": "wa-forward-live-1785214544", "kind": "forward_predicate_rollback", "status": "fail", "expected": "SearchInputFocused", "outcome": "no_effect", "forward
- seq=1452 `perception_unsettled`: {"ts": 1785215773.8119879, "seq": 1452, "run_id": "wa-forward-live-1785214544", "kind": "perception_unsettled", "status": "fail", "settled": false, "failure_modes": ["fusion_agreement_low"], "retry_st
- seq=1455 `transition_eval`: {"ts": 1785215773.837627, "seq": 1455, "run_id": "wa-forward-live-1785214544", "kind": "transition_eval", "status": "fail", "attempt": {"before_world_id": "w0", "after_world_id": "w0", "action_family"
- seq=1457 `verification`: {"ts": 1785215773.8378181, "seq": 1457, "run_id": "wa-forward-live-1785214544", "kind": "verification", "status": "fail", "passed": false, "reason": "no_effect", "expected_predicate": "TransitionEvalu
- seq=1463 `forward_predicate_rollback`: {"ts": 1785215774.5169659, "seq": 1463, "run_id": "wa-forward-live-1785214544", "kind": "forward_predicate_rollback", "status": "fail", "expected": "NoUnexpectedDialog", "outcome": "no_effect", "forwa
- seq=1487 `execution`: {"ts": 1785215791.521004, "seq": 1487, "run_id": "wa-forward-live-1785214544", "kind": "execution", "status": "fail", "ok": false, "backend": "ax", "message": "no editable field confirmed for 'Kulvind
- seq=1488 `transition_attribution`: {"ts": 1785215791.521538, "seq": 1488, "run_id": "wa-forward-live-1785214544", "kind": "transition_attribution", "status": "fail", "action_family": "type_query", "outcome": "no_effect", "effect_kind":
- seq=1519 `perception_unsettled`: {"ts": 1785215802.626996, "seq": 1519, "run_id": "wa-forward-live-1785214544", "kind": "perception_unsettled", "status": "fail", "settled": false, "failure_modes": ["fusion_agreement_low"], "retry_str
- seq=1522 `transition_eval`: {"ts": 1785215802.653007, "seq": 1522, "run_id": "wa-forward-live-1785214544", "kind": "transition_eval", "status": "fail", "attempt": {"before_world_id": "w0", "after_world_id": "w0", "action_family"
- seq=1524 `verification`: {"ts": 1785215802.653276, "seq": 1524, "run_id": "wa-forward-live-1785214544", "kind": "verification", "status": "fail", "passed": false, "reason": "no_effect", "expected_predicate": "TransitionEvalua
- seq=1530 `forward_predicate_rollback`: {"ts": 1785215803.3463502, "seq": 1530, "run_id": "wa-forward-live-1785214544", "kind": "forward_predicate_rollback", "status": "fail", "expected": "NoUnexpectedDialog", "outcome": "no_effect", "forwa
- seq=1556 `perception_unsettled`: {"ts": 1785215822.242571, "seq": 1556, "run_id": "wa-forward-live-1785214544", "kind": "perception_unsettled", "status": "fail", "settled": false, "failure_modes": ["fusion_agreement_low"], "retry_str
- seq=1559 `transition_eval`: {"ts": 1785215822.2718358, "seq": 1559, "run_id": "wa-forward-live-1785214544", "kind": "transition_eval", "status": "fail", "attempt": {"before_world_id": "w0", "after_world_id": "w0", "action_family
- seq=1561 `verification`: {"ts": 1785215822.272209, "seq": 1561, "run_id": "wa-forward-live-1785214544", "kind": "verification", "status": "fail", "passed": false, "reason": "no_effect", "expected_predicate": "TransitionEvalua
- seq=1567 `forward_predicate_rollback`: {"ts": 1785215822.8980422, "seq": 1567, "run_id": "wa-forward-live-1785214544", "kind": "forward_predicate_rollback", "status": "fail", "expected": "SearchInputFocused", "outcome": "no_effect", "forwa
- seq=1591 `execution`: {"ts": 1785215841.580199, "seq": 1591, "run_id": "wa-forward-live-1785214544", "kind": "execution", "status": "fail", "ok": false, "backend": "ax", "message": "no editable field confirmed for 'Kulvind
- seq=1592 `transition_attribution`: {"ts": 1785215841.585921, "seq": 1592, "run_id": "wa-forward-live-1785214544", "kind": "transition_attribution", "status": "fail", "action_family": "type_query", "outcome": "no_effect", "effect_kind":
- seq=1632 `perception_unsettled`: {"ts": 1785215854.389289, "seq": 1632, "run_id": "wa-forward-live-1785214544", "kind": "perception_unsettled", "status": "fail", "settled": false, "failure_modes": ["fusion_agreement_low"], "retry_str
- seq=1635 `transition_eval`: {"ts": 1785215854.416255, "seq": 1635, "run_id": "wa-forward-live-1785214544", "kind": "transition_eval", "status": "fail", "attempt": {"before_world_id": "w0", "after_world_id": "w0", "action_family"
- seq=1637 `verification`: {"ts": 1785215854.4165912, "seq": 1637, "run_id": "wa-forward-live-1785214544", "kind": "verification", "status": "fail", "passed": false, "reason": "no_effect", "expected_predicate": "TransitionEvalu
- seq=1644 `forward_predicate_rollback`: {"ts": 1785215854.5396218, "seq": 1644, "run_id": "wa-forward-live-1785214544", "kind": "forward_predicate_rollback", "status": "fail", "expected": "SearchInputFocused", "outcome": "no_effect", "forwa
- seq=1680 `execution`: {"ts": 1785215875.730978, "seq": 1680, "run_id": "wa-forward-live-1785214544", "kind": "execution", "status": "fail", "ok": false, "backend": "ax", "message": "no editable field confirmed for 'Kulvind
- seq=1681 `transition_attribution`: {"ts": 1785215875.736301, "seq": 1681, "run_id": "wa-forward-live-1785214544", "kind": "transition_attribution", "status": "fail", "action_family": "type_query", "outcome": "no_effect", "effect_kind":
- seq=1727 `perception_unsettled`: {"ts": 1785215886.910391, "seq": 1727, "run_id": "wa-forward-live-1785214544", "kind": "perception_unsettled", "status": "fail", "settled": false, "failure_modes": ["fusion_agreement_low"], "retry_str
- seq=1730 `transition_eval`: {"ts": 1785215886.9364312, "seq": 1730, "run_id": "wa-forward-live-1785214544", "kind": "transition_eval", "status": "fail", "attempt": {"before_world_id": "w0", "after_world_id": "w0", "action_family
- seq=1732 `verification`: {"ts": 1785215886.936832, "seq": 1732, "run_id": "wa-forward-live-1785214544", "kind": "verification", "status": "fail", "passed": false, "reason": "no_effect", "expected_predicate": "TransitionEvalua
- seq=1739 `forward_predicate_rollback`: {"ts": 1785215887.053996, "seq": 1739, "run_id": "wa-forward-live-1785214544", "kind": "forward_predicate_rollback", "status": "fail", "expected": "SearchInputFocused", "outcome": "no_effect", "forwar
- seq=1775 `execution`: {"ts": 1785215903.703556, "seq": 1775, "run_id": "wa-forward-live-1785214544", "kind": "execution", "status": "fail", "ok": false, "backend": "ax", "message": "no editable field confirmed for 'Kulvind
- seq=1776 `transition_attribution`: {"ts": 1785215903.706311, "seq": 1776, "run_id": "wa-forward-live-1785214544", "kind": "transition_attribution", "status": "fail", "action_family": "type_query", "outcome": "no_effect", "effect_kind":
- seq=1822 `perception_unsettled`: {"ts": 1785215915.901922, "seq": 1822, "run_id": "wa-forward-live-1785214544", "kind": "perception_unsettled", "status": "fail", "settled": false, "failure_modes": ["fusion_agreement_low"], "retry_str
- seq=1825 `transition_eval`: {"ts": 1785215915.9290419, "seq": 1825, "run_id": "wa-forward-live-1785214544", "kind": "transition_eval", "status": "fail", "attempt": {"before_world_id": "w0", "after_world_id": "w0", "action_family
- seq=1827 `verification`: {"ts": 1785215915.929505, "seq": 1827, "run_id": "wa-forward-live-1785214544", "kind": "verification", "status": "fail", "passed": false, "reason": "no_effect", "expected_predicate": "TransitionEvalua
- seq=1834 `forward_predicate_rollback`: {"ts": 1785215916.0515258, "seq": 1834, "run_id": "wa-forward-live-1785214544", "kind": "forward_predicate_rollback", "status": "fail", "expected": "SearchInputFocused", "outcome": "no_effect", "forwa
- seq=1870 `execution`: {"ts": 1785215932.6592698, "seq": 1870, "run_id": "wa-forward-live-1785214544", "kind": "execution", "status": "fail", "ok": false, "backend": "ax", "message": "no editable field confirmed for 'Kulvin
- seq=1871 `transition_attribution`: {"ts": 1785215932.662792, "seq": 1871, "run_id": "wa-forward-live-1785214544", "kind": "transition_attribution", "status": "fail", "action_family": "type_query", "outcome": "no_effect", "effect_kind":
- seq=1917 `perception_unsettled`: {"ts": 1785215944.082131, "seq": 1917, "run_id": "wa-forward-live-1785214544", "kind": "perception_unsettled", "status": "fail", "settled": false, "failure_modes": ["fusion_agreement_low"], "retry_str
- seq=1920 `transition_eval`: {"ts": 1785215944.1081119, "seq": 1920, "run_id": "wa-forward-live-1785214544", "kind": "transition_eval", "status": "fail", "attempt": {"before_world_id": "w0", "after_world_id": "w0", "action_family
- seq=1922 `verification`: {"ts": 1785215944.108279, "seq": 1922, "run_id": "wa-forward-live-1785214544", "kind": "verification", "status": "fail", "passed": false, "reason": "no_effect", "expected_predicate": "TransitionEvalua
- seq=1929 `forward_predicate_rollback`: {"ts": 1785215944.225506, "seq": 1929, "run_id": "wa-forward-live-1785214544", "kind": "forward_predicate_rollback", "status": "fail", "expected": "SearchInputFocused", "outcome": "no_effect", "forwar
- seq=1965 `execution`: {"ts": 1785215960.113795, "seq": 1965, "run_id": "wa-forward-live-1785214544", "kind": "execution", "status": "fail", "ok": false, "backend": "ax", "message": "no editable field confirmed for 'Kulvind
- seq=1966 `transition_attribution`: {"ts": 1785215960.116618, "seq": 1966, "run_id": "wa-forward-live-1785214544", "kind": "transition_attribution", "status": "fail", "action_family": "type_query", "outcome": "no_effect", "effect_kind":
- seq=2006 `perception_unsettled`: {"ts": 1785215971.875177, "seq": 2006, "run_id": "wa-forward-live-1785214544", "kind": "perception_unsettled", "status": "fail", "settled": false, "failure_modes": ["fusion_agreement_low"], "retry_str
- seq=2009 `transition_eval`: {"ts": 1785215971.905587, "seq": 2009, "run_id": "wa-forward-live-1785214544", "kind": "transition_eval", "status": "fail", "attempt": {"before_world_id": "w0", "after_world_id": "w0", "action_family"
- seq=2011 `verification`: {"ts": 1785215971.905952, "seq": 2011, "run_id": "wa-forward-live-1785214544", "kind": "verification", "status": "fail", "passed": false, "reason": "no_effect", "expected_predicate": "TransitionEvalua
- seq=2018 `forward_predicate_rollback`: {"ts": 1785215972.080561, "seq": 2018, "run_id": "wa-forward-live-1785214544", "kind": "forward_predicate_rollback", "status": "fail", "expected": "SearchInputFocused", "outcome": "no_effect", "forwar
- seq=2054 `execution`: {"ts": 1785215989.55893, "seq": 2054, "run_id": "wa-forward-live-1785214544", "kind": "execution", "status": "fail", "ok": false, "backend": "ax", "message": "no editable field confirmed for 'Kulvinde
- seq=2055 `transition_attribution`: {"ts": 1785215989.562525, "seq": 2055, "run_id": "wa-forward-live-1785214544", "kind": "transition_attribution", "status": "fail", "action_family": "type_query", "outcome": "no_effect", "effect_kind":
- seq=2101 `perception_unsettled`: {"ts": 1785216002.147666, "seq": 2101, "run_id": "wa-forward-live-1785214544", "kind": "perception_unsettled", "status": "fail", "settled": false, "failure_modes": ["fusion_agreement_low"], "retry_str
- seq=2104 `transition_eval`: {"ts": 1785216002.1735501, "seq": 2104, "run_id": "wa-forward-live-1785214544", "kind": "transition_eval", "status": "fail", "attempt": {"before_world_id": "w0", "after_world_id": "w0", "action_family
- seq=2106 `verification`: {"ts": 1785216002.173725, "seq": 2106, "run_id": "wa-forward-live-1785214544", "kind": "verification", "status": "fail", "passed": false, "reason": "no_effect", "expected_predicate": "TransitionEvalua
- seq=2113 `forward_predicate_rollback`: {"ts": 1785216002.2975092, "seq": 2113, "run_id": "wa-forward-live-1785214544", "kind": "forward_predicate_rollback", "status": "fail", "expected": "SearchInputFocused", "outcome": "no_effect", "forwa
- seq=2149 `execution`: {"ts": 1785216018.359047, "seq": 2149, "run_id": "wa-forward-live-1785214544", "kind": "execution", "status": "fail", "ok": false, "backend": "ax", "message": "no editable field confirmed for 'Kulvind
- seq=2150 `transition_attribution`: {"ts": 1785216018.360804, "seq": 2150, "run_id": "wa-forward-live-1785214544", "kind": "transition_attribution", "status": "fail", "action_family": "type_query", "outcome": "no_effect", "effect_kind":
- seq=2196 `perception_unsettled`: {"ts": 1785216029.147576, "seq": 2196, "run_id": "wa-forward-live-1785214544", "kind": "perception_unsettled", "status": "fail", "settled": false, "failure_modes": ["fusion_agreement_low"], "retry_str
- seq=2199 `transition_eval`: {"ts": 1785216029.176306, "seq": 2199, "run_id": "wa-forward-live-1785214544", "kind": "transition_eval", "status": "fail", "attempt": {"before_world_id": "w0", "after_world_id": "w0", "action_family"
- seq=2201 `verification`: {"ts": 1785216029.1766348, "seq": 2201, "run_id": "wa-forward-live-1785214544", "kind": "verification", "status": "fail", "passed": false, "reason": "no_effect", "expected_predicate": "TransitionEvalu
- seq=2208 `forward_predicate_rollback`: {"ts": 1785216029.349225, "seq": 2208, "run_id": "wa-forward-live-1785214544", "kind": "forward_predicate_rollback", "status": "fail", "expected": "SearchInputFocused", "outcome": "no_effect", "forwar
- seq=2244 `execution`: {"ts": 1785216046.7475688, "seq": 2244, "run_id": "wa-forward-live-1785214544", "kind": "execution", "status": "fail", "ok": false, "backend": "ax", "message": "no editable field confirmed for 'Kulvin
- seq=2245 `transition_attribution`: {"ts": 1785216046.750689, "seq": 2245, "run_id": "wa-forward-live-1785214544", "kind": "transition_attribution", "status": "fail", "action_family": "type_query", "outcome": "no_effect", "effect_kind":
- seq=2291 `perception_unsettled`: {"ts": 1785216059.1183271, "seq": 2291, "run_id": "wa-forward-live-1785214544", "kind": "perception_unsettled", "status": "fail", "settled": false, "failure_modes": ["fusion_agreement_low"], "retry_st
- seq=2294 `transition_eval`: {"ts": 1785216059.1455731, "seq": 2294, "run_id": "wa-forward-live-1785214544", "kind": "transition_eval", "status": "fail", "attempt": {"before_world_id": "w0", "after_world_id": "w0", "action_family
- seq=2296 `verification`: {"ts": 1785216059.146013, "seq": 2296, "run_id": "wa-forward-live-1785214544", "kind": "verification", "status": "fail", "passed": false, "reason": "no_effect", "expected_predicate": "TransitionEvalua
- seq=2303 `forward_predicate_rollback`: {"ts": 1785216059.269325, "seq": 2303, "run_id": "wa-forward-live-1785214544", "kind": "forward_predicate_rollback", "status": "fail", "expected": "SearchInputFocused", "outcome": "no_effect", "forwar
- seq=2339 `execution`: {"ts": 1785216076.094215, "seq": 2339, "run_id": "wa-forward-live-1785214544", "kind": "execution", "status": "fail", "ok": false, "backend": "ax", "message": "no editable field confirmed for 'Kulvind
- seq=2340 `transition_attribution`: {"ts": 1785216076.0976708, "seq": 2340, "run_id": "wa-forward-live-1785214544", "kind": "transition_attribution", "status": "fail", "action_family": "type_query", "outcome": "no_effect", "effect_kind"
- seq=2386 `perception_unsettled`: {"ts": 1785216086.9663959, "seq": 2386, "run_id": "wa-forward-live-1785214544", "kind": "perception_unsettled", "status": "fail", "settled": false, "failure_modes": ["fusion_agreement_low"], "retry_st
- seq=2389 `transition_eval`: {"ts": 1785216086.994268, "seq": 2389, "run_id": "wa-forward-live-1785214544", "kind": "transition_eval", "status": "fail", "attempt": {"before_world_id": "w0", "after_world_id": "w0", "action_family"
- seq=2391 `verification`: {"ts": 1785216086.9947488, "seq": 2391, "run_id": "wa-forward-live-1785214544", "kind": "verification", "status": "fail", "passed": false, "reason": "no_effect", "expected_predicate": "TransitionEvalu
- seq=2398 `forward_predicate_rollback`: {"ts": 1785216087.1458838, "seq": 2398, "run_id": "wa-forward-live-1785214544", "kind": "forward_predicate_rollback", "status": "fail", "expected": "SearchInputFocused", "outcome": "no_effect", "forwa
- seq=2434 `execution`: {"ts": 1785216105.218854, "seq": 2434, "run_id": "wa-forward-live-1785214544", "kind": "execution", "status": "fail", "ok": false, "backend": "ax", "message": "no editable field confirmed for 'Kulvind
- seq=2435 `transition_attribution`: {"ts": 1785216105.221589, "seq": 2435, "run_id": "wa-forward-live-1785214544", "kind": "transition_attribution", "status": "fail", "action_family": "type_query", "outcome": "no_effect", "effect_kind":
- seq=2475 `perception_unsettled`: {"ts": 1785216115.432079, "seq": 2475, "run_id": "wa-forward-live-1785214544", "kind": "perception_unsettled", "status": "fail", "settled": false, "failure_modes": ["fusion_agreement_low"], "retry_str
- seq=2478 `transition_eval`: {"ts": 1785216115.458503, "seq": 2478, "run_id": "wa-forward-live-1785214544", "kind": "transition_eval", "status": "fail", "attempt": {"before_world_id": "w0", "after_world_id": "w0", "action_family"
- seq=2480 `verification`: {"ts": 1785216115.458726, "seq": 2480, "run_id": "wa-forward-live-1785214544", "kind": "verification", "status": "fail", "passed": false, "reason": "no_effect", "expected_predicate": "TransitionEvalua
- seq=2487 `forward_predicate_rollback`: {"ts": 1785216115.57538, "seq": 2487, "run_id": "wa-forward-live-1785214544", "kind": "forward_predicate_rollback", "status": "fail", "expected": "SearchInputFocused", "outcome": "no_effect", "forward
- seq=2523 `execution`: {"ts": 1785216133.365948, "seq": 2523, "run_id": "wa-forward-live-1785214544", "kind": "execution", "status": "fail", "ok": false, "backend": "ax", "message": "no editable field confirmed for 'Kulvind
- seq=2524 `transition_attribution`: {"ts": 1785216133.368109, "seq": 2524, "run_id": "wa-forward-live-1785214544", "kind": "transition_attribution", "status": "fail", "action_family": "type_query", "outcome": "no_effect", "effect_kind":
- seq=2570 `perception_unsettled`: {"ts": 1785216146.324641, "seq": 2570, "run_id": "wa-forward-live-1785214544", "kind": "perception_unsettled", "status": "fail", "settled": false, "failure_modes": ["fusion_agreement_low"], "retry_str
- seq=2573 `transition_eval`: {"ts": 1785216146.3505669, "seq": 2573, "run_id": "wa-forward-live-1785214544", "kind": "transition_eval", "status": "fail", "attempt": {"before_world_id": "w0", "after_world_id": "w0", "action_family
- seq=2575 `verification`: {"ts": 1785216146.3508081, "seq": 2575, "run_id": "wa-forward-live-1785214544", "kind": "verification", "status": "fail", "passed": false, "reason": "no_effect", "expected_predicate": "TransitionEvalu
- seq=2582 `forward_predicate_rollback`: {"ts": 1785216146.475032, "seq": 2582, "run_id": "wa-forward-live-1785214544", "kind": "forward_predicate_rollback", "status": "fail", "expected": "SearchInputFocused", "outcome": "no_effect", "forwar
- seq=2584 `check`: {"ts": 1785216146.624906, "seq": 2584, "run_id": "wa-forward-live-1785214544", "kind": "check", "status": "fail", "name": "forward_task", "expected": "forward 'zarooratwala' from 'Kulvinder' to 'Palla
- seq=2585 `run_end`: {"ts": 1785216146.624955, "seq": 2585, "run_id": "wa-forward-live-1785214544", "kind": "run_end", "status": "fail", "ok": false, "detail": "closed_loop ok=False reason='Maximum step count reached' ite
