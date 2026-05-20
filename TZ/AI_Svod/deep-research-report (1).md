# Архитектура AI-анализа Jira-задач для сопровождения 1С

Для анализа задач из entity["software","Jira","issue-tracking software"] по направлению entity["software","1С:Предприятие","enterprise business automation platform"] я рекомендую не один «большой» LLM-запрос, а многошаговый конвейер: выборочная выгрузка, нормализация, поштучное извлечение фактов, кластеризация и только затем управленческая суммаризация. Это продиктовано самой структурой данных: в Jira Cloud поиск задач поддерживает выбор полей и пагинацию, комментарии и worklog’и доступны как отдельные paginated endpoints, а rich-text поля и комментарии в API v3 используют ADF. Со стороны моделей картина тоже неоднородна: через urlOpenRouter.aiturn0search0 доступны разные модели и провайдеры с разными `supported_parameters`, `context_length`, `per_request_limits`, правилами маршрутизации, fallback и политиками логирования/ретенции данных; для `:free`-вариантов отдельно документированы лимиты по RPM и дневным квотам. Отсюда прямой вывод: сырой массив задач нельзя надежно анализировать «одним промтом», его нужно поэтапно сжимать в структурированные артефакты. citeturn25view1turn19view2turn20view1turn15view7turn12view0turn14view3turn6view5turn6view6

## Целевая архитектура

**Общая архитектура решения**

Ниже — практический контур, который можно сразу отдавать в проектирование backend’а. Важная идея: каждый следующий этап работает не с «сырым текстом», а с более компактным и более управляемым представлением предыдущего этапа. Это одновременно снижает стоимость, повышает повторяемость результатов и позволяет заменять модели без переделки всей системы. Для облачного маршрутизатора особенно важно, что у моделей и провайдеров отличаются поддерживаемые параметры и ограничения, а значит orchestration должен быть внешним по отношению к LLM. citeturn6view0turn16view1turn13view2turn23view1

```text
Jira Extractor
  -> Raw Store
  -> Field Normalizer
  -> ADF/Markup Flattener
  -> Noise Remover + Dedupe
  -> Long-Text Compressor
  -> Task Context Builder
  -> LLM Task Analyzer
  -> JSON Validator
  -> Repair / Retry / Fallback
  -> Task Analysis Store
  -> Embeddings + Lexical Features
  -> Cluster Engine
  -> Batch / Cluster Summaries
  -> Final Management Summary
  -> Reports / Dashboard / DB
  -> Human QA Feedback Loop
```

В виде Map-Reduce это выглядит так:

```text
Map-0: выгрузить и нормализовать поля Jira
Map-1: превратить каждую задачу в компактный task_context
Map-2: проанализировать одну задачу и вернуть строгий JSON

Reduce-1: агрегировать 25–100 task JSON в batch summary
Reduce-2: объединить batch summary + кластеры + outliers
Reduce-3: собрать финальный управленческий отчет
```

Рекомендуемая последовательность этапов:

1. **Выгрузка из Jira.** Запрашивать только нужные поля, а комментарии и worklog’и получать отдельными запросами с пагинацией. Это уменьшает payload и упрощает контроль версии данных. citeturn25view1turn25view2turn19view2turn20view1  
2. **Сохранение сырья.** Хранить полный raw JSON ответа Jira неизменным — нужен для повторной нормализации, аудита и regression testing.  
3. **Предварительная очистка.** Преобразовать ADF/markup в текст, удалить служебный шум, нормализовать unicode, даты, роли сотрудников, 1С-сокращения и повторы. ADF-предобработка обязательна, потому что в Jira Cloud именно так хранятся комментарии и textarea-поля. citeturn15view7turn19view0turn20view0  
4. **Нормализация.** Собрать «канонический пакет контекста задачи»: title + goal + current behavior + description + сжатые comments/worklogs + технические метаданные.  
5. **Разбиение на чанки.** Если комментарии или журналы работ длинные, сначала прогонять их через отдельный компрессор, а основной анализ задачи уже делать по компактному представлению.  
6. **Анализ одной задачи.** Одна задача → один JSON строгой схемы. Это главный map-этап.  
7. **Пакетная агрегация.** Несколько десятков task JSON → batch summary: частоты, сигналы риска, черновые паттерны, кандидаты на кластеры.  
8. **Кластеризация и группировка.** Использовать одновременно controlled vocabulary, словарь синонимов 1С, embeddings и lexical features.  
9. **Финальное summary.** Сильная модель работает уже не по 10 000 сырых задач, а по компактному «слою аналитики»: cluster table, top outliers, quality stats, automation opportunities.  
10. **Проверка качества.** JSON-schema validation, полнота заполнения, sample review, disagreement checks, повторный прогон спорных кейсов.  
11. **Публикация.** Сохранять результат в БД, строить отчет, отдавать в дашборд и формировать review queue для аналитика.

**Главный проектный принцип**

LLM здесь не должен быть единственным источником истины. Он должен быть встроен как модуль извлечения и синтеза, а все критичные для надежности вещи — пагинация, дедупликация, учет токенов, ретраи, валидация, версионирование схемы, clustering state, cost logging — должны жить в приложении и базе данных. Это особенно важно, если вы хотите использовать дешевые модели через urlOpenRouter.aiturn0search0 или локальные рантаймы вместо одного «дорогого и всесильного» провайдера. citeturn12view0turn13view5turn24view0turn23view1

## Каноническая модель данных

**Какие данные передавать в модель**

В облачную модель нужно передавать не весь raw issue, а **task context packet**. Если вы отправляете исходные ADF-блоки, длинные бот-комментарии, автоуведомления и повторы, вы тратите контекст на мусор и ухудшаете качество классификации. Кроме того, у провайдеров могут различаться политики логирования и ретенции, поэтому ФИО, email, телефоны, ссылки на внутренние адреса и любые чувствительные реквизиты лучше псевдонимизировать или удалять до отправки, если только вы не используете локальный inference или строгое `data_collection: "deny"`/ZDR. citeturn15view7turn13view1turn6view5turn6view6

Ниже — практическое правило по полям.

**Наименование задачи**

Обязательно передавать. Это самый плотный носитель сигнала для первичной классификации. Чистить нужно префиксы вроде `[INC]`, `[1C]`, `RE:`, служебные номера, авто-добавленные статусы, копипасту шаблонов. Риск — название может быть слишком общим вроде «Ошибка» или «Не работает». Сокращать объем можно агрессивно: оставить только информативную часть, но не терять ключевые термины 1С, подсистему, интеграцию и симптом.

**Цель задачи**

Передавать, если поле заполнено. Оно нужно, чтобы разделять «сломалось» и «нужно доработать/настроить/объяснить». Чистить канцеляризмы, убирать повтор title, выносить конкретный бизнес-результат в 1–2 предложения. Риск — часто цель записана как желаемое поведение без контекста. Сокращать можно до формата: *бизнес-цель + объект изменения*.

**Текущее поведение**

Передавать обязательно, если это инцидент, баг, расхождение или ошибка. Это сильнейший сигнал для `issue_type`, `risk_level` и `root_cause_hypothesis`. Чистить нужно так, чтобы отделить факты от интерпретаций: что именно происходит, где, при каком действии, с какой частотой. Риск — пользователи смешивают ожидаемое и фактическое поведение. Сокращать можно до формулы: *действие → наблюдаемый симптом → область 1С*.

**Описание**

Передавать почти всегда. Это основная несущая часть контекста. Чистить надо шаблонные вводные блоки, подписи, повторяющиеся фрагменты переписки, избыточные вставки логов, куски ADF/HTML, ненужные цитаты. Риск — описание может быть длинным, разрозненным и содержащим несколько тем. Сокращать лучше в два шага: сначала нормализация, потом каноническое summary на 5–10 предложений.

**Журналы работ**

Передавать не в raw-виде, а в сжатой форме. Они нужны для оценки трудоемкости, цепочки действий сотрудников и финального результата. Чистить нужно шаблонные записи времени, дубли, неинформативные «исследование», «созвон», «проверка» без содержания. Риск — worklog часто содержит важный итог, которого нет ни в title, ни в description. Объем уменьшать через извлечение событий вида: *дата → действие → результат → timeSpent*, сохраняя итоговую запись и все записи про фиксы/обходные решения.

**Комментарии сотрудников**

Передавать выборочно. Комментарии нужны для уточнений, признаков повторяемости, гипотез причины, подтверждения фикса и определения, кто ждал кого. Чистить следует автоматические уведомления, цитаты предыдущих сообщений, приветствия, обсуждения «не по теме», копии одного и того же описания. Риск — комментарии противоречат друг другу и часто не имеют явного финала. Объем нужно уменьшать с помощью фильтра «содержательный комментарий» и отдельного `comments_digest`, где остаются только: постановка проблемы, уточнение условий, найденная причина, предпринятые действия, подтверждение решения, unresolved status.

Практическое правило по тому, что отправлять в модель:

- **Всегда:** `task_id`, cleaned `title`, `goal`, `current_behavior`, cleaned `description`.
- **Условно обязательно:** `comments_digest`, `worklogs_digest`.
- **Опционально:** 1–3 последних содержательных комментария и 1–3 ключевые записи worklog, если они короткие.
- **Не отправлять напрямую в облако:** персональные данные, пароли, внутренние URL, сырые дампы логов, большие вложения, длинные stack trace целиком.

**Какие данные стоит дополнительно собирать в Jira**

Текущих полей достаточно для базового семантического анализа, но их мало для качественной управленческой аналитики. Я бы сделал обязательными или как минимум настоятельно рекомендованными такие поля:

- `environment`: prod / test / dev  
- `1c_product`: БП / ЗУП / УТ / ERP / УНФ / ДО / кастомная конфигурация  
- `1c_version` и `extension_presence`  
- `business_process`: продажи, закупки, зарплата, казначейство, регламентированная отчетность и т. п.  
- `request_source`: пользователь / внутренний аудит / мониторинг / регуляторика / интеграция  
- `impact_scope`: один пользователь / отдел / компания / отчетный период / блокирующий контур  
- `root_cause_category`: данные / права / код / интеграция / обновление / регламент / пользовательская ошибка / неизвестно  
- `resolution_type`: исправлено / workaround / консультация / отклонено / ожидает клиента / перенесено в доработку  
- `duplicate_of` или `problem_parent_id`  
- `time_split`: диагностика / исправление / тест / коммуникации  
- `kb_link`: статья базы знаний, если появилась  
- `automation_candidate_flag`  
- `closure_reason`  
- `caused_by_update_flag`

Если эти поля начать заполнять последовательно, качество кластеризации, автоматизации и RCA-аналитики вырастет кратно, потому что исчезнет необходимость каждый раз «угадать» бизнес-процесс и класс причины из свободного текста.

**Формат промежуточной структуры одной задачи**

Я бы использовал строгий JSON с машинными кодами в значениях и отдельным слоем отображения в UI. Это даст стабильную аналитику, а русские human-friendly названия можно маппить уже на дашборде.

```json
{
  "task_id": "SUP-1234",
  "title": "Ошибка обмена с банком после обновления",
  "short_summary": "После обновления конфигурации перестала загружаться банковская выписка; найден временный обходной путь, но системное исправление не подтверждено.",
  "business_goal": "Восстановить корректную загрузку банковских выписок без ручной обработки.",
  "current_behavior": "Импорт выписки завершается ошибкой формата обмена.",
  "canonical_problem_statement": "Сломан типовой обмен с банком после обновления конфигурации.",
  "issue_type": "integration_failure",
  "work_type": "incident_resolution",
  "affected_1c_area": ["treasury", "bank_exchange", "updates_extensions"],
  "business_process": "bank_operations",
  "root_cause_hypothesis": "Несовместимость формата обмена или расширения после обновления.",
  "employee_actions": [
    "Проверили настройки обмена",
    "Сравнили поведение до и после обновления",
    "Протестировали обходной ручной импорт",
    "Передали в доработку"
  ],
  "final_status_or_outcome": "workaround_found",
  "recurring_problem_markers": [
    "after_update",
    "bank_exchange",
    "format_mismatch"
  ],
  "risk_level": "high",
  "complexity_level": "medium",
  "automation_potential": "medium",
  "documentation_needed": "high",
  "tags": [
    "bank_exchange",
    "after_update",
    "format_error",
    "treasury"
  ],
  "confidence_score": 0.82,
  "missing_information": [
    "Нет подтверждения окончательного исправления",
    "Не указана версия конфигурации"
  ],
  "evidence_snippets": [
    "В комментариях указано, что проблема появилась после обновления",
    "В worklog есть запись о временном ручном обходе"
  ],
  "source_quality": "medium",
  "taxonomy_version": "v1.0"
}
```

Пояснение к полям:

- `task_id` — стабильный идентификатор задачи. Лучше issue key, а не внутренний numeric id.
- `title` — очищенное название без служебного шума.
- `short_summary` — суть задачи в 1–3 предложениях.
- `business_goal` — зачем вообще была инициирована работа.
- `current_behavior` — что фактически происходит сейчас.
- `canonical_problem_statement` — нормализованная формулировка проблемы для кластеризации.
- `issue_type` — тип проблемы: инцидент, баг, интеграция, права, данные, производительность, консультация и т. д.
- `work_type` — характер выполненной работы: диагностика, устранение инцидента, консультация, настройка, разработка, документирование и т. д.
- `affected_1c_area` — одна или несколько зон 1С.
- `business_process` — прикладной процесс, а не техническая подсистема.
- `root_cause_hypothesis` — аккуратная гипотеза причины; если нет доказательств, это должна быть именно гипотеза.
- `employee_actions` — 3–8 нормализованных действий сотрудников.
- `final_status_or_outcome` — чем закончилась задача на самом деле.
- `recurring_problem_markers` — короткие маркеры повторяемости, полезные для кластеров и поиска паттернов.
- `risk_level` — low / medium / high / critical.
- `complexity_level` — low / medium / high.
- `automation_potential` — none / low / medium / high.
- `documentation_needed` — none / low / medium / high.
- `tags` — компактные нормализованные теги.
- `confidence_score` — первичная самооценка модели, но потом ее нужно скорректировать backend’ом.
- `missing_information` — чего не хватает, чтобы трактовка была надежной.
- `evidence_snippets` — короткие текстовые якоря для QA.
- `source_quality` — poor / medium / good в зависимости от полноты исходной карточки.
- `taxonomy_version` — версия словаря категорий, чтобы не ломать историческую аналитику.

Отдельно рекомендую хранить рядом не только `analysis_json`, но и **normalized text fingerprint** задачи. Он нужен для дедупликации, повторной индексации и сравнений между прогонами.

## Анализ одной задачи

**Этап анализа отдельной задачи**

Для этого этапа нужно добиваться максимальной детерминированности: одна задача на входе, один JSON на выходе, controlled vocabulary, запрет на выдумывание фактов, обязательное заполнение `missing_information`. Если выбранная модель или провайдер поддерживает schema-constrained output, его нужно включать. Это явно документировано для совместимых моделей в urlOpenRouter.aiturn0search4, а для локальных рантаймов — в urlOllamaturn0search2 и urlLM Studioturn2search4. Если structured outputs недоступны, нужен backend-validator и отдельный repair-pass. citeturn6view1turn6view15turn6view12turn13view2

**Системный промт для анализа одной Jira-задачи**

```text
Ты — аналитический модуль в AI-пайплайне анализа Jira-задач по направлению «Сопровождение 1С».

Ты получаешь РОВНО ОДНУ задачу. Твоя цель — извлечь факты, убрать шум и вернуть строго один валидный JSON-объект.

Работай по правилам:

1. Используй ТОЛЬКО информацию из входных полей.
2. Не выдумывай отсутствующие факты.
3. Если факт не подтвержден, используй null, "unknown" или добавь пункт в missing_information.
4. Если есть несколько версий причины, дай наиболее вероятную гипотезу в root_cause_hypothesis, но не выдавай ее за доказанный факт.
5. Игнорируй служебный шум:
   - автоуведомления;
   - приветствия/прощания;
   - повторяющиеся цитаты;
   - служебные статусы без содержательного смысла;
   - неинформативные записи вида «проверено», «созвон», «ок».
6. Сохраняй только содержательные действия и факты.
7. Если комментарии и worklog противоречат друг другу, отрази это в missing_information и понизь confidence_score.
8. short_summary должен содержать только суть проблемы и исход.
9. employee_actions должен быть массивом коротких нормализованных действий в прошедшем времени.
10. recurring_problem_markers должен содержать только повторяемые паттерны, а не уникальные детали одной задачи.
11. confidence_score должен быть числом от 0 до 1.
12. Верни только JSON. Без markdown, без пояснений, без текста до и после JSON.

Используй следующие допустимые значения:

issue_type:
- incident
- bug
- integration_failure
- access_issue
- data_issue
- performance_issue
- consultation
- change_request
- reporting_issue
- update_issue
- user_error
- unknown

work_type:
- incident_resolution
- investigation
- configuration
- development
- consultation
- data_fix
- testing
- documentation
- communication
- monitoring
- unknown

affected_1c_area:
- accounting
- payroll_hr
- sales
- procurement
- warehouse
- manufacturing
- treasury
- bank_exchange
- regulated_reporting
- integrations
- master_data
- access_rights
- print_forms
- scheduled_jobs
- updates_extensions
- administration
- unknown

business_process:
- month_close
- payroll
- sales_order
- procurement
- warehouse_operations
- bank_operations
- regulated_reporting
- master_data_management
- user_access_management
- cross_system_exchange
- internal_consulting
- unknown

risk_level:
- low
- medium
- high
- critical

complexity_level:
- low
- medium
- high

automation_potential:
- none
- low
- medium
- high

documentation_needed:
- none
- low
- medium
- high

source_quality:
- poor
- medium
- good

Формат полей:
- task_id: string
- title: string
- short_summary: string
- business_goal: string|null
- current_behavior: string|null
- canonical_problem_statement: string
- issue_type: string
- work_type: string
- affected_1c_area: array[string]
- business_process: string
- root_cause_hypothesis: string|null
- employee_actions: array[string]
- final_status_or_outcome: string|null
- recurring_problem_markers: array[string]
- risk_level: string
- complexity_level: string
- automation_potential: string
- documentation_needed: string
- tags: array[string]
- confidence_score: number
- missing_information: array[string]
- evidence_snippets: array[string]
- source_quality: string
- taxonomy_version: string

Дополнительные ограничения:
- affected_1c_area: минимум 1 значение
- tags: от 3 до 10 значений
- evidence_snippets: от 0 до 5 коротких пунктов
- short_summary: не более 450 символов
- canonical_problem_statement: не более 220 символов
- root_cause_hypothesis: не более 220 символов
- employee_actions: не более 8 элементов
- missing_information: не более 8 элементов
- если исход задачи не дает оснований определить финальный результат, ставь final_status_or_outcome = null
- если задача похожа на консультацию, но содержит исправление, issue_type и work_type должны отражать суть, а не тон переписки

Верни строго один JSON-объект.
```

**Пользовательский промт для анализа одной Jira-задачи**

```text
Проанализируй одну Jira-задачу по сопровождению 1С и верни строго JSON по заданной схеме.

TASK_ID:
{{task_id}}

TITLE:
{{clean_title}}

GOAL:
{{clean_goal_or_null}}

CURRENT_BEHAVIOR:
{{clean_current_behavior_or_null}}

DESCRIPTION:
{{clean_description_or_null}}

WORKLOGS_DIGEST:
{{worklogs_digest_or_null}}

COMMENTS_DIGEST:
{{comments_digest_or_null}}

OPTIONAL_LAST_SIGNIFICANT_COMMENTS:
{{top_significant_comments_or_null}}

OPTIONAL_LAST_SIGNIFICANT_WORKLOGS:
{{top_significant_worklogs_or_null}}

NORMALIZATION_HINTS:
- если встречаются синонимы 1С, своди их к одной нормализованной сущности;
- если проблема описана в разных формулировках, выбери одну каноническую формулировку;
- если виден временный обходной путь, не называй это окончательным решением;
- если отсутствует явный итог, обязательно укажи это в missing_information;
- если задача содержит только обсуждение и вопрос пользователя, это не development по умолчанию;
- если worklog или comments содержат прямой итог, используй его для final_status_or_outcome.

OUTPUT:
Верни только один JSON-объект.
```

**Практические замечания к этому этапу**

- Если `description + comments/worklogs` после очистки все еще велико, сначала прогоняйте отдельный substep `comments/worklogs -> digest`, а уже потом основной prompt.
- Для дешевых моделей не нужно заставлять их писать длинные reasoning-ответы. Лучше требовать короткие поля и строгие словари.
- Если JSON невалиден, не отправляйте задачу сразу в ручную обработку: сначала repair-pass, потом fallback-модель, и только затем manual queue.

## Масштабирование, кластеризация и итоговая управленческая аналитика

**Этап пакетной обработки задач**

Здесь важно разделить объём по уровням.

**Для 100 задач**

Это почти «ручной» объём. Можно:
- проанализировать каждую задачу по одной;
- собрать 3–5 batch summary;
- построить кластеры по всему пулу;
- получить один финальный отчет.

**Для 1 000 задач**

Нужна уже штатная иерархия:
- Stage A: поштучный анализ всех задач;
- Stage B: micro-batches по 25–50 task JSON для дешевых моделей с коротким контекстом;
- Stage C: cluster-level reduce;
- Stage D: final management summary по кластерным данным, а не по task-level сырью.

**Для 10 000+ задач**

Нужен инкрементальный режим:
- поштучный map только для новых и измененных задач;
- embeddings и кластеризация — инкрементально ежедневно;
- полная перекластеризация — раз в неделю или раз в месяц;
- управленческий отчет — по окнам времени и по последнему слепку кластеров.

Рекомендация по размеру батчей:

- **raw stage**: почти всегда **1 задача на 1 запрос**;
- **micro-task stage**: 2–3 задачи на запрос только если после очистки каждая занимает < 400–500 токенов;
- **batch summary stage**:  
  - 25–40 task JSON для 8k-контекста;  
  - 50–80 task JSON для 16k;  
  - 80–150 task JSON для 32k;  
- **cluster labeling**: 10–30 representative tasks + cluster stats;
- **final summary**: только агрегаты, cluster table, outlier list и quality stats.

Практическая формула:

```text
effective_input_budget =
  min(
    0.5 * model_context_window,
    model_context_window - reserve_system - reserve_output
  )

batch_size =
  floor(effective_input_budget / avg_task_json_tokens)
```

Где:
- `reserve_system` — 1 000–2 000 токенов;
- `reserve_output` — 15–25% окна;
- `avg_task_json_tokens` — средний размер compact task JSON.

**Когда анализировать по одной задаче, а когда группами**

По одной задаче надо анализировать всё, что:
- содержит длинные комментарии;
- относится к high/critical risk;
- похоже на уникальный или редкий кейс;
- имеет плохое качество исходных данных;
- содержит много технических деталей 1С или интеграций.

Группами разумно анализировать только:
- очень короткие консультации;
- типовые сервисные обращения;
- уже нормализованные JSON-описания, а не raw-тексты.

**Как хранить промежуточные результаты**

Для каждого шага хранить:
- `source_hash` нормализованного входа;
- `prompt_version`;
- `taxonomy_version`;
- `model_id`;
- `provider`;
- `response_raw`;
- `json_valid`;
- `repair_count`;
- `confidence_score`;
- `created_at`.

Так вы сможете:
- не гонять заново неизменившиеся задачи;
- сравнивать модели;
- делать rollback после изменения словаря;
- понимать, где именно появилась ошибка.

**Как не потерять редкие, но важные проблемы**

Это одна из главных ловушек. Если смотреть только на частоту, вы потеряете критичные единичные кейсы. Поэтому я рекомендую всегда вести как минимум четыре независимых рейтинга:

- по **частоте**;
- по **риску**;
- по **трудоемкости**;
- по **редкости × критичности**.

Дополнительно нужен **outlier queue**:
- всё, что не попало в кластеры;
- всё, что имеет `risk_level in (high, critical)` при низкой частоте;
- всё, что имеет низкий `confidence_score`;
- всё, что выглядит как потенциальная системная причина после обновления, интеграции или регуляторного изменения.

**Как избежать доминирования популярных, но не критичных задач**

Итоговый отчет должен иметь отдельные блоки:
- «самые частые»;
- «самые дорогие по трудозатратам»;
- «самые рискованные»;
- «редкие, но опасные».

Иначе «много мелких консультаций» перекроет, например, единичные, но критичные сбои обменов, расчетов зарплаты или регламентированной отчетности.

**Как делать повторный анализ после накопления новых задач**

Рекомендую три ритма:
- **ежедневно** — обрабатывать новые/измененные задачи;
- **еженедельно** — обновлять кластеры и агрегаты;
- **ежемесячно** — собирать полный управленческий отчет и пересчитывать словарь синонимов.

Повторный прогон обязателен также при изменении:
- taxonomy version;
- prompt version;
- модели;
- правил очистки.

**Этап кластеризации и группировки**

Я бы делал кластеризацию не по одному полю, а по **combined representation**:

```text
cluster_text =
  canonical_problem_statement
  + issue_type
  + work_type
  + affected_1c_area
  + business_process
  + root_cause_hypothesis
  + recurring_problem_markers
  + tags
```

Далее — три слоя группировки.

**Слой правил**

Сначала справочник синонимов и доменных эквивалентов 1С:

```text
"БП", "бухгалтерия", "1С Бухгалтерия" -> accounting
"ЗУП", "зарплата", "кадры" -> payroll_hr
"банк-клиент", "обмен с банком", "загрузка выписок" -> bank_exchange
"права", "доступ", "роль", "не вижу документ" -> access_rights
"обновление", "после обновления", "расширение сломалось" -> updates_extensions
```

Этот слой критичен именно для сопровождения 1С, потому что одна и та же проблема почти всегда называется по-разному.

**Лексический слой**

Затем строить TF-IDF по `cluster_text`. Это дешевый, объяснимый и устойчивый baseline для поиска близких формулировок и near-duplicates. В urlscikit-learnturn10search0 `TfidfVectorizer` прямо описан как преобразование коллекции raw documents в матрицу TF-IDF признаков. citeturn15view4

**Семантический слой**

Поверх лексики — embeddings. Их можно получать либо через embeddings API в urlOpenRouter.aiturn11search0, либо локально через urlText Embeddings Inferenceturn11search2. Для хранения и поиска по векторам практичны urlpgvectorturn9search0 для расширения к entity["software","PostgreSQL","open-source relational database"] и urlFaissturn9search1 для высокопроизводительного similarity search. citeturn12view2turn15view1turn15view2turn9search0turn15view3

**Алгоритм кластеризации**

По умолчанию я бы использовал HDBSCAN на embeddings плюс lexical similarity как дополнительный фильтр. В документации urlscikit-learnturn10search8 HDBSCAN описан как более устойчивый к подбору параметров и умеющий работать с кластерами разной плотности; DBSCAN остается легким fallback и тоже хорош в шумных данных и для выбросов. Для коротких корпусов или CPU-only режима достаточно TF-IDF + DBSCAN. citeturn15view6turn15view5

Практические разрезы группировки:

- по `issue_type`
- по `work_type`
- по `affected_1c_area`
- по `business_process`
- по `root_cause_hypothesis`
- по `recurring_problem_markers`
- по `risk_level`
- по `complexity_level`
- по суммарной трудоемкости
- по `automation_potential`
- по `documentation_needed`

**Как объединять похожие формулировки**

Использовать каскад:

1. exact match по нормализованным тегам;  
2. словарь синонимов 1С;  
3. cosine similarity по TF-IDF;  
4. cosine similarity по embeddings;  
5. LLM cluster-labeling по exemplar set.

То есть LLM не должен сам «вслепую» строить все кластеры. Он должен подписывать и объединять кластеры, которые уже предварительно найдены статистическими методами.

**Этап финального управленческого summary**

Финальный LLM-слой должен читать не задачи, а уже такой набор данных:

- cluster table;
- top frequent categories;
- top risky categories;
- top effort categories;
- unresolved categories;
- outlier queue;
- automation candidates;
- documentation candidates;
- Jira data quality findings;
- sample representative tasks for each top cluster.

Я рекомендую делать финал в **два шага**:
1. strong model возвращает **management_report_json**;
2. deterministic renderer превращает его в Markdown/PDF/дашборд.

Это гораздо лучше, чем просить модель сразу делать «красивый отчет», потому что вы сможете:
- сравнивать версии отчетов;
- подкрашивать dashboard по полям JSON;
- стабильно строить периодические отчеты.

**Системный промт для финального summary**

```text
Ты — управленческий аналитик направления «Сопровождение 1С».

Ты НЕ анализируешь сырые Jira-задачи. Ты анализируешь только агрегированные данные:
- кластеры;
- статистику частот;
- статистику трудоемкости;
- статистику рисков;
- кандидатов на автоматизацию;
- кандидатов в базу знаний;
- проблемы качества данных Jira;
- редкие, но критичные outlier-кейсы.

Твои правила:
1. Используй только переданные агрегаты.
2. Не выдумывай цифры, причины и выводы, если они не следуют из входа.
3. Всегда разделяй:
   - частое;
   - трудоемкое;
   - рискованное;
   - редкое, но критичное.
4. Если данных недостаточно, прямо укажи это.
5. Если проблема редкая, но потенциально системная, обязательно выдели ее отдельно.
6. Рекомендации должны быть практическими и управленческими.
7. Все выводы должны быть привязаны к наблюдаемым паттернам кластеров.
8. Верни результат в JSON.

Структура ответа:
- executive_summary
- main_work_types
- frequent_problems
- labor_intensive_categories
- risky_categories
- recurring_request_causes
- knowledge_base_candidates
- automation_candidates
- process_change_recommendations
- jira_data_quality_issues
- jira_field_recommendations
- manager_recommendations
- improvement_plan_30_60_90
```

**Пользовательский промт для финального summary**

```text
Собери управленческий отчет по направлению «Сопровождение 1С».

CONTEXT:
- period: {{period}}
- scope: {{scope}}
- total_tasks: {{total_tasks}}
- analyzed_tasks: {{analyzed_tasks}}
- taxonomy_version: {{taxonomy_version}}

INPUT_DATA:
- cluster_table: {{cluster_table_json}}
- high_risk_outliers: {{outliers_json}}
- top_by_frequency: {{top_by_frequency_json}}
- top_by_effort: {{top_by_effort_json}}
- top_by_risk: {{top_by_risk_json}}
- automation_candidates: {{automation_candidates_json}}
- documentation_candidates: {{documentation_candidates_json}}
- jira_data_quality_stats: {{jira_data_quality_json}}
- representative_examples: {{representative_examples_json}}

REQUIREMENTS:
Сформируй:
1. Executive summary.
2. Главные типы работ по направлению.
3. Самые частые проблемы.
4. Наиболее трудоемкие категории.
5. Наиболее рискованные категории.
6. Повторяющиеся причины обращений.
7. Что стоит вынести в инструкции / базу знаний.
8. Что стоит автоматизировать.
9. Что стоит изменить в процессе сопровождения.
10. Какие данные в Jira сейчас заполняются плохо.
11. Какие поля Jira стоит добавить или сделать обязательными.
12. Рекомендации для руководителя направления.
13. План улучшений на 30 / 60 / 90 дней.

Верни строго JSON.
```

## OpenRouter и альтернативные контуры

**Архитектура с учетом OpenRouter.ai**

Через urlOpenRouter.aiturn0search0 удобно строить единый LLM gateway: API нормализован под один формат, models API отдает `pricing`, `context_length`, `per_request_limits`, `supported_parameters`, а маршрутизация поддерживает provider sorting, fallbacks, privacy filters и guardrails. Для чувствительных Jira-данных это важно, потому что можно не только выбирать цену/скорость, но и ограничивать провайдеров по параметрам, data collection и ZDR-политике. citeturn6view0turn12view0turn13view1turn6view5turn6view6turn12view7

Практическая стратегия по этапам:

**Дешевые или слабые модели**

Им можно отдавать:
- очистку коротких задач;
- digest comments/worklogs;
- task-level extraction для типовых, не слишком длинных кейсов;
- repair-pass JSON;
- cluster labeling второго эшелона;
- регулярные nightly backfills.

Критерии выбора:
- поддержка structured output или минимум корректного JSON;
- стабильность на русском и техно-лексике;
- умеренная цена;
- достаточное окно контекста под один task packet.

**Более сильные модели**

Им лучше отдавать:
- сложные задачи с длинной перепиской;
- тонкие кейсы с противоречивыми комментариями;
- cluster merge / cluster naming;
- финальный management summary;
- RCA-подобные сводки;
- рекомендации по изменению процесса.

Критерий здесь другой: не «самая дешевая», а «лучшее качество синтеза на агрегатах».

**Как выбирать модели, не привязываясь к устаревающему списку**

Не хардкодить названия как «бесплатные навсегда». Вместо этого на этапе запуска сервиса делать runtime-фильтрацию через models API:
- достаточно ли `context_length`;
- есть ли нужные `supported_parameters`;
- не стоит ли жесткий `per_request_limits`;
- устраивает ли цена;
- допустим ли provider privacy policy. citeturn16view1turn16view0turn12view0

**Как проектировать fallback между моделями**

Для extractor-этапа рекомендую схему:

```text
primary_extractor_model
  -> fallback_extractor_model
  -> fallback_general_model
```

На уровне OpenRouter это лучше задавать не вручную через try/catch-хаос, а через `models: [...]`. В документации это явно описано как automatic failover, когда первая модель недоступна, rate-limited или отказывается отвечать. Если вы хотите жестко требовать поддержку параметров JSON/структурированного вывода, включайте `provider.require_parameters = true`, чтобы провайдеры не «игнорировали» неизвестные параметры молча. citeturn6view3turn13view2

**Как учитывать лимиты**

Сервис должен:
- проверять `/api/v1/key` на остаток лимитов/кредитов;
- хранить локальный rate limiter по stage и модели;
- учитывать, что для `:free`-вариантов в OpenRouter задокументированы отдельные лимиты: 20 RPM и дневные квоты, зависящие от наличия купленных кредитов. citeturn14view2turn14view3

**Как логировать ошибки и повторять запросы**

Базовая политика retry:

- `429` / `503` — уважать `Retry-After`;
- `408` / `502` — exponential backoff;
- JSON invalid — repair-pass;
- repeated invalid JSON — fallback model;
- repeated semantic disagreement — manual queue.

OpenRouter явно документирует `Retry-After` для 429/503 и стандартную JSON-форму ошибок. citeturn13view5turn12view4

**Как проверять валидность JSON**

Если structured output поддерживается, используйте его. Если нет:
1. parse JSON;
2. validate against JSON schema;
3. normalize enums;
4. repair missing commas/braces;
5. rerun only invalid tasks.

Если ваши запросы должны соблюдать структурированный формат, обязательно фильтруйте кандидатов по `supported_parameters` и/или включайте `require_parameters`, иначе часть провайдеров может проигнорировать нужный parameter silently. citeturn16view1turn6view1turn13view2

**Как версионировать и наблюдать pipeline**

Очень полезны:
- presets для stage-конфигураций в OpenRouter;
- user/session tagging для связки с batch/run ids;
- usage/accounting в model_runs;
- generation ID для post-hoc аудита.

Presets позволяют отделять конфигурацию маршрутизации и системных промтов от кода, а usage accounting и generation endpoint дают prompt/completion token counts, cost, cache status, provider, latency и прочую метаинформацию. Для Responses API доступны `metadata` и `session_id`, что удобно для группировки запросов по батчу или отчету. citeturn12view6turn24view0turn22view3turn22view4turn22view1

**Как использовать response caching**

У OpenRouter есть response caching в бета-режиме: identical requests can be returned from cache with zero billable usage counters. Для task-analysis это не основной способ экономии, потому что сами задачи уникальны. Но кэш полезен для:
- повторяемых repair-запросов;
- deterministic rerender финального summary;
- regression testing на frozen benchmark prompts. citeturn12view5

**Как сравнивать качество моделей на тестовой выборке**

Нужен frozen benchmark, например 150–300 вручную размеченных задач, где есть:
- истинный `issue_type`;
- истинный `work_type`;
- правильная зона 1С;
- наличие/отсутствие итогового решения;
- оценка риска;
- факт повторяемости.

По нему мерить:
- JSON valid rate;
- schema completeness;
- agreement with human labels;
- hallucination rate;
- cost per 1 000 tasks;
- p95 latency;
- repair-pass frequency.

**Альтернативные решения помимо OpenRouter.ai**

**Локальные open-source модели через urlOllamaturn0search2**

Плюсы:
- локальный запуск;
- OpenAI-compatible API;
- structured outputs по JSON schema для локального inference;
- минимум сетевой зависимости. citeturn6view15turn6view16turn15view0

Минусы:
- качество сильно зависит от выбранных весов и железа;
- для сложного управленческого synthesis часто понадобится модель заметно сильнее;
- в документации отдельно отмечено, что Ollama Cloud currently does not support structured outputs. citeturn6view15

Когда использовать:
- если Jira-данные чувствительные;
- если основной поток — массовая дешевая поштучная обработка;
- как map-stage extractor в гибридной схеме.

**Локальные модели через urlLM Studioturn2search4**

Плюсы:
- легко поднять local LLM API server;
- есть OpenAI-compatible и Anthropic-compatible endpoints;
- есть JSON schema structured output;
- удобно для on-prem pilot и внутренних аналитических стендов. citeturn6view11turn6view12turn2search8

Минусы:
- для headless server workloads обычно менее удобен, чем полноценный серверный inference stack;
- требует аккуратного контроля загрузки, если используется несколькими воркерами.

Когда использовать:
- быстрый PoC;
- внутренние пилоты;
- рабочие места аналитиков;
- on-prem environments без сложной оркестрации.

**Облачный serverless через urlHugging Face Inference Providersturn0search3**

Плюсы:
- единый доступ к сотням моделей;
- pay-as-you-go;
- в pricing docs заявлено centralized transparent pricing without markup;
- хороший запас по экспериментам и failover между провайдерами. citeturn6view13turn6view14

Минусы:
- облачный контур;
- качество и latency по моделям и провайдерам могут заметно отличаться;
- free-tier/квоты нужно проверять на момент внедрения, а не зашивать в дизайн.

Когда использовать:
- быстрый выбор из большого числа моделей;
- тестирование quality/cost frontier;
- резервный облачный контур.

**Локальные embeddings через urlText Embeddings Inferenceturn11search2**

Плюсы:
- можно гонять embeddings локально;
- есть dynamic batching;
- есть Prometheus metrics и tracing;
- есть локальный CPU/GPU deployment. citeturn15view1turn15view2

Минусы:
- это не генеративный движок для summary;
- нужен отдельный LLM для extraction/synthesis.

Когда использовать:
- dedupe;
- similarity search;
- инкрементальная кластеризация;
- retrieval по backlog’у исторических задач.

**Гибридная схема**

Это мой базовый recommendation:

- локальный слабый/средний extractor для задач;
- локальный embeddings service;
- облачная сильная модель только для cluster synthesis и финального management report.

Такой вариант почти всегда дает лучший баланс стоимости, приватности и качества.

**Embeddings + vector database**

Если задач тысячи и десятки тысяч, embeddings нужны не «для моды», а для:
- near-duplicate detection;
- инкрементальной кластеризации;
- поиска похожих исторических кейсов;
- retrieval примеров в batch summary;
- cluster drift monitoring.

Для старта достаточно `pgvector`; если объем и latency требования растут — можно увести часть similarity search в Faiss. citeturn9search0turn15view3

**Классические NLP-методы**

Их нельзя выбрасывать. Они особенно полезны как дешевый baseline:
- regex/rule-based normalization;
- synonym dictionaries;
- TF-IDF;
- DBSCAN/HDBSCAN;
- keyword extraction;
- MinHash/near-duplicate detection.

Именно эти методы должны делать предварительную «грязную работу», а не LLM.

## Техническая реализация и контроль качества

**Рекомендуемая техническая архитектура**

Если делать сервис «по-взрослому», я бы проектировал его как набор сервисов/воркеров, а не как один большой backend endpoint.

```text
[ Jira Extractor ]
    -> [ Raw Storage ]
    -> [ Cleaning / Normalization Worker ]
    -> [ Long-Text Compression Worker ]
    -> [ LLM Gateway ]
    -> [ JSON Validation / Repair Worker ]
    -> [ Embeddings Worker ]
    -> [ Cluster Engine ]
    -> [ Report Builder ]
    -> [ Dashboard API / UI ]
    -> [ QA Review Queue ]
```

Практический стек можно выбрать разный, но логика обычно такая:

- **backend orchestration** — Python/FastAPI, Node/NestJS или любой сервисный backend;
- **очередь задач** — Redis Queue / RabbitMQ / Kafka, в зависимости от объема и требований к replay;
- **реляционная БД** — обычно entity["software","PostgreSQL","open-source relational database"];
- **векторное хранение** — `pgvector` или отдельное similarity-хранилище;
- **сырое хранилище** — object storage для raw JSON, больших экспортов и отчетов;
- **UI аналитики** — embedded dashboard или собственный React/Vue frontend;
- **мониторинг** — cost, latency, JSON valid rate, queue lag, cluster drift, review backlog.

Если route идёт через urlOpenRouter.aiturn0search0, то `model_runs` можно хорошо наполнять из встроенного `usage`-объекта и generation metadata: token counts, costs, cached tokens, provider, router, latency и generation id приходят либо прямо в ответах, либо через `/generation`. Это сильно упрощает cost-analytics и debugging. citeturn24view0turn24view2turn22view3

**Структура базы данных**

Ниже — примерная схема таблиц, которую удобно реализовать с самого начала.

**`jira_tasks_raw`**

Ключевые поля:
- `task_id` PK
- `issue_key`
- `project_key`
- `raw_issue_json`
- `raw_comments_json`
- `raw_worklogs_json`
- `source_updated_at`
- `ingested_at`
- `raw_hash`
- `ingest_run_id`

Назначение: хранение эталонного сырья для пересборки pipeline.

**`jira_tasks_cleaned`**

Ключевые поля:
- `task_id` PK
- `clean_title`
- `clean_goal`
- `clean_current_behavior`
- `clean_description`
- `comments_digest`
- `worklogs_digest`
- `merged_task_context`
- `language`
- `source_quality_estimate`
- `noise_flags_json`
- `clean_hash`
- `cleaned_at`

Назначение: «канонический пакет» перед LLM.

**`ai_task_analysis`**

Ключевые поля:
- `task_id` PK/FK
- `analysis_json`
- `issue_type`
- `work_type`
- `affected_1c_area_json`
- `business_process`
- `risk_level`
- `complexity_level`
- `automation_potential`
- `documentation_needed`
- `confidence_score`
- `taxonomy_version`
- `prompt_version`
- `model_run_id`
- `analyzed_at`

Назначение: основной task-level артефакт.

**`ai_batches`**

Ключевые поля:
- `batch_id` PK
- `batch_type` (`task_analysis`, `batch_summary`, `cluster_labeling`, `final_report`)
- `scope_json`
- `task_count`
- `input_ids_json`
- `status`
- `started_at`
- `finished_at`
- `retry_count`
- `cost_total`
- `token_total`

Назначение: трассировка всех reduce-шагов.

**`ai_clusters`**

Ключевые поля:
- `cluster_id` PK
- `cluster_label`
- `cluster_type`
- `cluster_summary`
- `issue_type`
- `work_type`
- `affected_1c_area_json`
- `business_process`
- `task_ids_sample_json`
- `frequency`
- `avg_risk_score`
- `avg_confidence`
- `effort_total`
- `automation_share`
- `documentation_share`
- `outlier_flag`
- `built_from_snapshot`
- `updated_at`

Назначение: семантическая модель повторяющихся паттернов.

**`ai_reports`**

Ключевые поля:
- `report_id` PK
- `scope_type`
- `period_from`
- `period_to`
- `report_json`
- `report_markdown`
- `dashboard_payload_json`
- `generated_by_model_run_id`
- `status`
- `created_at`

Назначение: управленческие отчеты и их версии.

**`model_runs`**

Ключевые поля:
- `model_run_id` PK
- `stage`
- `provider`
- `model_id`
- `api_type`
- `request_hash`
- `source_hash`
- `prompt_version`
- `response_valid_json`
- `repair_applied`
- `generation_id`
- `prompt_tokens`
- `completion_tokens`
- `reasoning_tokens`
- `cached_tokens`
- `cost`
- `latency_ms`
- `http_status`
- `error_code`
- `created_at`

Назначение: полное cost/quality/latency наблюдение по инференсу.

**`quality_checks`**

Ключевые поля:
- `check_id` PK
- `target_type` (`task`, `batch`, `cluster`, `report`)
- `target_id`
- `schema_valid`
- `completeness_score`
- `evidence_alignment_score`
- `hallucination_flag`
- `manual_review_status`
- `reviewer_id`
- `quality_score`
- `details_json`
- `created_at`

Назначение: QA, regression и review queue.

**Контроль качества AI-анализа**

Качество здесь должно проверяться в несколько слоев.

**Валидность JSON**

Первое сито:
- корректный parse;
- соответствие schema;
- допустимые enum values;
- отсутствие лишних полей, если включен strict mode.

**Полнота заполнения**

Проверять долю непустых ключевых полей:
- `short_summary`
- `issue_type`
- `work_type`
- `affected_1c_area`
- `risk_level`
- `final_status_or_outcome`
- `missing_information`

Если модель часто оставляет пустые поля — это либо слабая модель, либо плохой prompt, либо слишком грязной вход.

**Confidence score**

Не принимайте model self-score как истину. Лучше считать итоговый engineering score так:

```text
final_confidence =
  model_confidence
  - penalty_for_missing_fields
  - penalty_for_conflicting_sources
  - penalty_for_low_source_quality
  - penalty_for_invalid_repair_history
  + bonus_for_explicit_outcome
  + bonus_for_clear_root_cause_signal
```

**Ручная проверка выборки**

Нужен регламент:
- 5–10% новых задач на ручной review;
- 100% задач с `risk_level = critical`;
- review sample для крупнейших кластеров;
- review sample для outlier queue.

**Сравнение разных моделей**

Для frozen benchmark сравнивать:
- JSON validity rate
- field completeness rate
- label agreement
- hallucination rate
- cost/task
- p95 latency
- repair-pass rate

**Повторный прогон спорных задач**

Повторный прогон нужен, если:
- score < threshold;
- `risk_level` высокий, а `confidence_score` низкий;
- `missing_information` содержит критичный пробел;
- задача попала в outlier queue;
- два прогона разошлись по ключевым полям.

**Проверка на галлюцинации**

Практический способ:
- каждая ключевая интерпретация должна иметь `evidence_snippets`;
- verifier-проход должен проверять: «утверждение следует из входа?»;
- если root cause или outcome не подтверждены — они должны остаться гипотезой/null.

**Scoring-система качества анализа задачи**

Я бы использовал шкалу 0–100:

```text
15  JSON validity
10  Schema completeness
10  Enum compliance
20  Evidence alignment
10  Outcome extraction quality
10  Root-cause plausibility
10  Confidence calibration
10  Cluster consistency
5   Noise removal quality
```

Интерпретация:
- **85–100** — принимаем автоматически;
- **70–84** — принимаем с флагом;
- **50–69** — repair/retry;
- **<50** — manual review.

Дополнительные метрики системы:
- `% valid_json`
- `% auto-accepted`
- `% repair_needed`
- `% manual_review`
- `avg cost per task`
- `p95 latency`
- `cluster purity`
- `outlier review rate`
- `report drift month-over-month`

## Длинные тексты, финальные артефакты и сквозной сценарий

**Обработка больших объемов текста**

Для Jira Cloud это не optional pre-processing. Комментарии и worklog’и имеют отдельные paginated endpoints, а комментарии и rich-text поля хранятся как ADF-документы, поэтому сначала нужен слой flattening + filtering, иначе вы будете оплачивать анализ технической обвязки вместо смысла. citeturn19view2turn20view1turn15view7turn19view0turn20view0

Рабочая стратегия:

**Очистка служебных сообщений**

Удалять:
- автоуведомления о смене статуса;
- системные подписи;
- пустые или почти пустые комментарии;
- уведомления о назначении;
- повторяющиеся цитаты;
- комментарии только с «ок», «проверено», «спасибо».

**Удаление дублей**

Использовать:
- exact hash dedupe;
- normalized text hash;
- near-duplicate similarity порогом 0.92–0.97;
- separate dedupe для comments и worklogs.

**Выделение только содержательных комментариев**

Простейший rule-based classifier:
- длина > N символов;
- содержит факт/ошибку/действие/результат;
- не является чистым статусным boilerplate;
- не совпадает с предыдущим комментарием.

**Предварительное summary комментариев**

Лучше делать отдельно:
- `comments -> comment_events`
- `worklogs -> worklog_events`

Формат события:

```json
{
  "date": "2026-05-01",
  "type": "diagnosis|clarification|fix|workaround|confirmation|waiting",
  "actor_role": "analyst|developer|user|unknown",
  "content": "Короткий факт",
  "result": "Что изменилось"
}
```

Потом уже эти события редуцировать в `comments_digest` и `worklogs_digest`.

**Разделение комментариев по датам**

Это полезно для определения:
- первичного симптома;
- точки эскалации;
- найденной причины;
- обходного пути;
- подтверждения исправления.

Особенно важно сохранять:
- самый ранний осмысленный комментарий;
- комментарий, где впервые названа причина;
- комментарий/запись worklog с финальным результатом;
- последний осмысленный комментарий.

**Извлечение действий сотрудников**

Фокус не на «кто сказал», а на «что сделали»:
- проверили настройки;
- воспроизвели ошибку;
- обновили расширение;
- перепровели документы;
- настроили права;
- очистили кеш;
- перезапустили регламентное задание;
- дали инструкцию пользователю.

**Извлечение финального результата**

Итог может быть только в одном месте:
- последний комментарий;
- последняя запись worklog;
- фраза вроде «ошибка подтверждена/не воспроизводится/передано в разработку/использовать обходной вариант».

Поэтому финальный outcome лучше извлекать отдельной логикой, а не только из полного summary.

**Ограничение токенов**

Рекомендуемый target size на одну задачу после сжатия:
- core context: 500–900 токенов;
- comments digest: 200–500 токенов;
- worklogs digest: 150–400 токенов;
- total task packet: 1 000–1 800 токенов.

Если больше — сначала еще один компрессор.

**Иерархическая суммаризация**

Рекомендованная цепочка:

```text
raw comments/worklogs
  -> event extraction
  -> comments/worklogs digest
  -> task analysis JSON
  -> batch summary
  -> cluster summary
  -> management report
```

Это ровно тот случай, где иерархическая суммаризация работает лучше, чем любой single-shot prompt.

**Финальные артефакты**

На выходе сервиса должны появляться как минимум следующие сущности:

- **JSON по каждой задаче** — основной нормализованный артефакт.
- **Таблица кластеров** — cluster id, label, summary, frequency, avg risk, avg effort.
- **Сводный отчет** — management report JSON и rendered Markdown/PDF.
- **Список частых проблем** — отдельный machine-readable список.
- **Список рекомендаций** — с приоритезацией.
- **Список задач на автоматизацию** — backlog automation opportunities.
- **Список тем для базы знаний** — канонические KB topics.
- **Список проблем качества заполнения Jira** — missing fields, noisy comments, inconsistent closure.
- **Управленческий дашборд** — минимум 5 представлений:
  - типы работ;
  - частые проблемы;
  - риск × частота;
  - трудоемкость по категориям;
  - качество заполнения Jira.

Дополнительно полезны:
- review queue;
- regression benchmark report;
- cluster drift report;
- monthly change log по паттернам обращений.

**Пример end-to-end сценария**

Ниже — реалистичный сквозной сценарий для 500 задач.

**Берем 500 задач**

Extractor делает JQL-запрос на выборку и тянет только нужные поля. Отдельно догружает comments и worklogs с пагинацией. Сырой ответ сохраняется в `jira_tasks_raw`. На этом шаге важно не пытаться сразу отправить все 500 задач в LLM. citeturn25view1turn19view2turn20view1

**Чистим данные**

Normalizer:
- разворачивает ADF в текст;
- убирает автоуведомления;
- вычищает дубли;
- псевдонимизирует имена;
- строит `comments_digest` и `worklogs_digest`;
- сохраняет результат в `jira_tasks_cleaned`.

Предположим:
- 320 задач короткие и чистые;
- 140 требуют digest по комментариям;
- 40 очень длинные и идут через усиленный компрессор.

**Анализируем каждую задачу**

LLM worker берет по одной задаче:
- отправляет task packet;
- получает строгий JSON;
- валидирует его.

Из 500 задач, например:
- 440 сразу валидны;
- 45 проходят repair-pass;
- 12 уходят на fallback-модель;
- 3 идут в manual review.

**Сохраняем JSON**

Каждый результат записывается в `ai_task_analysis`, а метаинформация по запросу — в `model_runs`. Если один и тот же task packet уже анализировался и `source_hash` не изменился, задача пропускается.

**Группируем**

Embeddings worker строит вектора по `cluster_text`, lexical engine считает TF-IDF, cluster engine делает HDBSCAN/DBSCAN и создает:
- около 20–40 рабочих кластеров;
- несколько крупных cluster families;
- отдельный outlier queue на редкие кейсы.

Дальше LLM подписывает кластеры и формирует cluster summaries.

**Делаем summary**

Report builder получает:
- cluster table;
- top frequency;
- top effort;
- top risk;
- rare critical outliers;
- data quality stats;
- automation/doc candidates.

Сильная модель строит `management_report_json`, а renderer делает:
- короткий executive summary;
- подробный Markdown;
- payload для dashboard.

**Проверяем качество**

QA pipeline:
- случайно выбирает 50 задач;
- сравнивает task JSON с raw source;
- проверяет крупнейшие 10 кластеров;
- перепроверяет все critical/outlier кейсы;
- формирует `quality_checks`.

Если, например, выясняется, что модель часто завышает `automation_potential`, можно:
- поправить prompt;
- пересчитать только affected subset;
- не трогать весь архив.

**Формируем отчет**

На выходе руководитель получает:
- сводный отчет;
- список топ-проблем;
- список тем для базы знаний;
- список automation opportunities;
- список проблем качества заполнения Jira;
- 30/60/90 plan.

А сервис получает обратную связь:
- какие кластеры признаны «неудачными»;
- какие поля в JSON требуют доработки;
- какие Jira-поля надо сделать обязательными.

**Итоговая рекомендация**

Наиболее практичный вариант для вашего кейса — это гибридный, schema-first pipeline:

- Jira как источник сырья;
- rule-based normalization и словарь 1С до LLM;
- одна задача → один JSON;
- дешевые модели на массовом map-этапе;
- embeddings + clustering вне LLM;
- сильная модель только на cluster-level и management summary;
- строгая БД промежуточных результатов;
- QA-петля с ручной выборочной проверкой.

Такой дизайн устойчив к грязным данным, масштабируется от сотен до десятков тысяч задач, не зависит от одной модели и хорошо совместим как с urlOpenRouter.aiturn0search0, так и с локальными/гибридными схемами на базе urlOllamaturn0search2, urlLM Studioturn2search4, urlHugging Face Inference Providersturn0search3 и локальных embedding-движков вроде urlText Embeddings Inferenceturn11search2. citeturn6view15turn6view12turn6view13turn15view1turn23view1turn24view0