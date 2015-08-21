AJS.$("#select2-users").auiSelect2();

function toggleHidden(e) {
    $('.toggle').toggleClass('hidden');
}

$('.spy a.aui-inline-dialog-trigger, .alias-list a.aui-inline-dialog-trigger, a.cancel').on('click', toggleHidden);

$('ul.aliases li').on('click', function(e) {
    toggleHidden();

});

(function () {

    $(document).ready(function () {
        var signedRequest = $("meta[name=acpt]").attr("content");
        $.ajaxSetup({
            beforeSend: function (request) {
                request.setRequestHeader("X-acpt", signedRequest);
            }
        });
    });

    $('form').on('submit', function (e) {
        e.stopPropagation();
        e.preventDefault();
        $.ajax({
            type: 'POST',
            url: '/create',
            data: JSON.stringify({
                alias: $('input#alias-name').val(),
                mentions: $('#select2-users').val(),
                room: $('input#room').val()
            }),
            success: function() {
                toggleHidden();
                window.location.reload();
            }
        });
    });

})();
