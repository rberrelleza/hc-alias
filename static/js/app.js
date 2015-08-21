AJS.$("#select2-users").auiSelect2();

function toggleHidden(e) {
    $('.toggle').toggleClass('hidden');
}

$('.spy a.aui-inline-dialog-trigger, a.cancel').on('click', toggleHidden);