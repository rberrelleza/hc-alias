AJS.$("#select2-users").auiSelect2();

function toggleHidden(e) {
    $('.toggle').toggleClass('hidden');
}

$('.spy a.aui-inline-dialog-trigger, .alias-list a.aui-inline-dialog-trigger, a.cancel').on('click', toggleHidden);

(function () {

    $(document).ready(function () {
        var signedRequest = $("meta[name=acpt]").attr("content");
        $.ajaxSetup({
            beforeSend: function (request) {
                request.setRequestHeader("X-acpt", signedRequest);
            }
        });
    });

})();
