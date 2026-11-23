// UI strings. Hindi values that are still English are marked TODO (native check in P6c).
// Stop names are never translated; they come from GTFS.
var I18N = {
  en: {
    'app.city': 'Delhi',
    'skip': 'Skip to journeys',
    'tab.planner': 'Plan a trip',
    'tab.operator': 'Operators',
    'tab.data': 'Data & method',
    'lang.group': 'Language',
    'from': 'From',
    'to': 'To',
    'swap': 'Swap From and To',
    'stop.placeholder': 'Type a stop name',
    'stop.none': 'No stop matches “{q}”',
    'pick_on_map': 'Pick on map',
    'pick.hint': 'Click the map near a stop to set {field}',
    'pick.set': '{field} set to {stop}',
    'daytype': 'Day',
    'daytype.weekday': 'Weekday',
    'daytype.saturday': 'Saturday',
    'daytype.sunday': 'Sunday or holiday',
    'leave_at': 'Leave at',
    'search': 'Search',
    'edit': 'Edit',
    'enquiry.label': 'Your search',
    'pref.label': 'Sort by',
    'pref.fastest': 'Fastest',
    'pref.comfort': 'Most comfortable',
    'col.dep': 'Dep',
    'col.arr': 'Arr',
    'col.min': 'Min',
    'col.chg': 'Chg',
    'col.avail': 'Availability',
    'options.label': 'Journey options',
    'options.count': '{n} options, sorted by {pref}',
    'level.MANY_SEATS_AVAILABLE': 'Many seats',
    'level.FEW_SEATS_AVAILABLE': 'Few seats',
    'level.STANDING_ROOM_ONLY': 'Standing room',
    'level.CRUSHED_STANDING_ROOM_ONLY': 'Very crowded',
    'level.NO_DATA_AVAILABLE': 'Limited data',
    'short.MANY_SEATS_AVAILABLE': 'Seats',
    'short.FEW_SEATS_AVAILABLE': 'Few seats',
    'short.STANDING_ROOM_ONLY': 'Standing',
    'short.CRUSHED_STANDING_ROOM_ONLY': 'Crowded',
    'short.NO_DATA_AVAILABLE': 'Limited data',
    'avail.k': 'seats {k}/10',
    'seats_k_of_10': 'Seats on {k} of 10 trips',
    'crowded_between': 'Crowded from {a} to {b}',
    'range': 'Usually {a} to {b}',
    'confidence.high': 'High confidence',
    'confidence.medium': 'Medium confidence',
    'confidence.low': 'Low confidence',
    'confidence.n': 'from {n} sampled riders',
    'limited.low_n': 'Too few sampled tickets on this stretch to estimate crowding.',
    'limited.schedule_gap': 'The timetable shows no bus in this slot, so crowding can’t be estimated.',
    'limited.generic': 'Not enough ticket data here to estimate crowding.',
    'leave_later': 'Leave at {t} → likely seat',
    'leave_later.more': 'seats on {k} of 10 trips, arrives {m} min later',
    'board_upstream': 'Walk {m} min to {stop} and board there → seat more likely',
    'board_upstream.more': 'seats on {k} of 10 trips',
    'quiet_hour': 'At {t} this trip is usually: {level}',
    'quiet_hour.more': '{m} min',
    'changes': '{n} change(s)',
    'changes.0': 'Direct',
    'walk_min': 'Walk {m} min',
    'walk.to': 'Walk {m} min to {stop}',
    'walk.dest': 'Walk {m} min to your destination',
    'walk.transfer': 'Walk {m} min to change at {stop}',
    'bus.towards': 'towards {h}',
    'bus.board': 'Board {t} at {stop}',
    'bus.alight': 'Get off {t} at {stop}',
    'bus.alight_notime': 'Get off at {stop}',
    'bus.ride': '{m} min ride',
    'strip.label': 'Crowding stop by stop: {s}',
    'strip.calm': 'seats likely all the way',
    'strip.partial': 'seats likely on the stretches with data; limited data elsewhere',
    'strip.some_nd': 'limited data elsewhere',
    'strip.until': 'seats likely until {a}, crowded {a} to {b}',
    'strip.from': 'crowded {a} to {b}',
    'strip.none': 'not enough data to show crowding stop by stop',
    'strip.cell': '{a} → {b} ∙ {level} ∙ {m} min',
    'on_map': 'Shown on map',
    'no_route': 'No bus route found within 2 hours',
    'no_route.why': 'No trip in the timetable joins these stops in this window.',
    'no_route.later': 'Search 1 hour later',
    'no_route.edit': 'Change stops',
    'err.same': 'From and To are the same stop. Choose a different destination.',
    'err.outside': 'That point is outside the bus network. Pick a spot inside Delhi.',
    'err.need_stop': 'Choose a stop from the list for {field}.',
    'err.api': 'Couldn’t load journeys. Check your connection and try again.',
    'err.stops': 'Couldn’t load the stop list. Search will work once it loads.',
    'err.retry': 'Try again',
    'loading': 'Finding buses…',
    'data_note': 'Estimated from October 2026 app tickets, scaled to all riders',
    'fixture.banner': 'Synthetic sample data. These numbers are made up to test the layout and are not estimates.',
    'map.label': 'Map of the selected journey',
    'map.legend': 'Crowding',
    'map.trip': 'Your trip',
    'map.walk': 'Walk',
    'map.expand': 'Expand map',
    'map.collapse': 'Shrink map',
    'map.unavailable': 'The map couldn’t load. Every journey detail is in the list.',
    'operator.title': 'Where one more bus helps most',
    'operator.shell': 'The segment heatmap by hour and the top 20 route-hours ranked by +1-bus benefit appear here once the operator data is connected.',
    'data.title': 'Data and method',
    'data.shell': 'Coverage, the expansion factor and who is missing from the ticket data appear here once /coverage is connected.'
  },
  hi: {
    'app.city': 'दिल्ली',
    'skip': 'Skip to journeys', // TODO hi
    'tab.planner': 'यात्रा खोजें',
    'tab.operator': 'ऑपरेटर',
    'tab.data': 'डेटा और तरीका',
    'lang.group': 'Language', // TODO hi
    'from': 'कहाँ से',
    'to': 'कहाँ तक',
    'swap': 'बदलें',
    'stop.placeholder': 'Type a stop name', // TODO hi
    'stop.none': 'No stop matches “{q}”', // TODO hi
    'pick_on_map': 'Pick on map', // TODO hi
    'pick.hint': 'Click the map near a stop to set {field}', // TODO hi
    'pick.set': '{field} set to {stop}', // TODO hi
    'daytype': 'Day', // TODO hi
    'daytype.weekday': 'कार्यदिवस',
    'daytype.saturday': 'शनिवार',
    'daytype.sunday': 'रविवार या छुट्टी',
    'leave_at': 'निकलने का समय',
    'search': 'खोजें',
    'edit': 'Edit', // TODO hi
    'enquiry.label': 'Your search', // TODO hi
    'pref.label': 'Sort by', // TODO hi
    'pref.fastest': 'सबसे तेज़',
    'pref.comfort': 'सबसे आरामदायक',
    'col.dep': 'Dep', // TODO hi
    'col.arr': 'Arr', // TODO hi
    'col.min': 'Min', // TODO hi
    'col.chg': 'Chg', // TODO hi
    'col.avail': 'Availability', // TODO hi
    'options.label': 'Journey options', // TODO hi
    'options.count': '{n} options, sorted by {pref}', // TODO hi
    'level.MANY_SEATS_AVAILABLE': 'कई सीटें खाली',
    'level.FEW_SEATS_AVAILABLE': 'कुछ सीटें खाली',
    'level.STANDING_ROOM_ONLY': 'खड़े होने की जगह',
    'level.CRUSHED_STANDING_ROOM_ONLY': 'बहुत भीड़',
    'level.NO_DATA_AVAILABLE': 'डेटा कम है',
    'short.MANY_SEATS_AVAILABLE': 'कई सीटें खाली',
    'short.FEW_SEATS_AVAILABLE': 'कुछ सीटें खाली',
    'short.STANDING_ROOM_ONLY': 'खड़े होने की जगह',
    'short.CRUSHED_STANDING_ROOM_ONLY': 'बहुत भीड़',
    'short.NO_DATA_AVAILABLE': 'डेटा कम है',
    'avail.k': 'seats {k}/10', // TODO hi
    'seats_k_of_10': '10 में से {k} यात्राओं में सीट मिलती है',
    'crowded_between': '{a} से {b} तक भीड़',
    'range': 'Usually {a} to {b}', // TODO hi
    'confidence.high': 'भरोसा: ज़्यादा',
    'confidence.medium': 'भरोसा: मध्यम',
    'confidence.low': 'भरोसा: कम',
    'confidence.n': 'from {n} sampled riders', // TODO hi
    'limited.low_n': 'Too few sampled tickets on this stretch to estimate crowding.', // TODO hi
    'limited.schedule_gap': 'The timetable shows no bus in this slot, so crowding can’t be estimated.', // TODO hi
    'limited.generic': 'Not enough ticket data here to estimate crowding.', // TODO hi
    'leave_later': '{t} बजे निकलें → सीट मिलने की संभावना',
    'leave_later.more': 'seats on {k} of 10 trips, arrives {m} min later', // TODO hi
    'board_upstream': '{m} मिनट चलकर {stop} से चढ़ें → सीट मिलने की संभावना ज़्यादा',
    'board_upstream.more': 'seats on {k} of 10 trips', // TODO hi
    'quiet_hour': '{t} बजे यह यात्रा आमतौर पर: {level}',
    'quiet_hour.more': '{m} min', // TODO hi
    'changes': '{n} बार बस बदलें',
    'changes.0': 'Direct', // TODO hi
    'walk_min': 'पैदल {m} मिनट',
    'walk.to': 'Walk {m} min to {stop}', // TODO hi
    'walk.dest': 'Walk {m} min to your destination', // TODO hi
    'walk.transfer': 'Walk {m} min to change at {stop}', // TODO hi
    'bus.towards': 'towards {h}', // TODO hi
    'bus.board': 'Board {t} at {stop}', // TODO hi
    'bus.alight': 'Get off {t} at {stop}', // TODO hi
    'bus.alight_notime': 'Get off at {stop}', // TODO hi
    'bus.ride': '{m} min ride', // TODO hi
    'strip.label': 'Crowding stop by stop: {s}', // TODO hi
    'strip.calm': 'seats likely all the way', // TODO hi
    'strip.partial': 'seats likely on the stretches with data; limited data elsewhere', // TODO hi
    'strip.some_nd': 'limited data elsewhere', // TODO hi
    'strip.until': 'seats likely until {a}, crowded {a} to {b}', // TODO hi
    'strip.from': 'crowded {a} to {b}', // TODO hi
    'strip.none': 'not enough data to show crowding stop by stop', // TODO hi
    'strip.cell': '{a} → {b} ∙ {level} ∙ {m} min', // TODO hi
    'on_map': 'Shown on map', // TODO hi
    'no_route': '2 घंटे में कोई बस रूट नहीं मिला',
    'no_route.why': 'No trip in the timetable joins these stops in this window.', // TODO hi
    'no_route.later': 'Search 1 hour later', // TODO hi
    'no_route.edit': 'Change stops', // TODO hi
    'err.same': 'From and To are the same stop. Choose a different destination.', // TODO hi
    'err.outside': 'That point is outside the bus network. Pick a spot inside Delhi.', // TODO hi
    'err.need_stop': 'Choose a stop from the list for {field}.', // TODO hi
    'err.api': 'Couldn’t load journeys. Check your connection and try again.', // TODO hi
    'err.stops': 'Couldn’t load the stop list. Search will work once it loads.', // TODO hi
    'err.retry': 'Try again', // TODO hi
    'loading': 'Finding buses…', // TODO hi
    'data_note': 'अक्टूबर 2026 के ऐप टिकटों से अनुमान, सभी यात्रियों के हिसाब से',
    'fixture.banner': 'Synthetic sample data. These numbers are made up to test the layout and are not estimates.', // TODO hi
    'map.label': 'Map of the selected journey', // TODO hi
    'map.legend': 'Crowding', // TODO hi
    'map.trip': 'Your trip', // TODO hi
    'map.walk': 'Walk', // TODO hi
    'map.expand': 'Expand map', // TODO hi
    'map.collapse': 'Shrink map', // TODO hi
    'map.unavailable': 'The map couldn’t load. Every journey detail is in the list.', // TODO hi
    'operator.title': 'Where one more bus helps most', // TODO hi
    'operator.shell': 'The segment heatmap by hour and the top 20 route-hours ranked by +1-bus benefit appear here once the operator data is connected.', // TODO hi
    'data.title': 'Data and method', // TODO hi
    'data.shell': 'Coverage, the expansion factor and who is missing from the ticket data appear here once /coverage is connected.' // TODO hi
  }
};

var lang = 'en';

function t(k, v) {
  var s = (I18N[lang] && I18N[lang][k]) || I18N.en[k] || k;
  return v ? s.replace(/\{(\w+)\}/g, function (m, n) { return v[n] == null ? m : v[n]; }) : s;
}
